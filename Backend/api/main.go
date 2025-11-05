package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/gorilla/mux"
	pq "github.com/lib/pq"
)

var db *sql.DB

// Add cache structure
type CacheEntry struct {
	Data      []CarDataEntry
	Timestamp time.Time
	LaneID    string
}

var (
	dataCache     = make(map[string]CacheEntry)
	cacheMutex    sync.RWMutex
	cacheDuration = 2 * time.Second // Cache for 2 seconds
)

// Estrutura que representa cada registro individual
type CarDataEntry struct {
	ID             int     `json:"id"`
	CurrentCars    int     `json:"current_cars"`
	RollingAverage float64 `json:"rolling_average"`
	TotalCount     int     `json:"total_count"`
	Timestamp      string  `json:"timestamp"`
	LaneID         string  `json:"lane_id"`
}

// Middleware para habilitar CORS
func enableCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

		// Handle preflight requests
		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		next.ServeHTTP(w, r)
	})
}

func main() {
	// Configurar conexão com PostgreSQL
	host := getEnv("DB_HOST", "localhost")
	port := getEnv("DB_PORT", "5432")
	user := getEnv("DB_USER", "projete")
	password := getEnv("DB_PASSWORD", "12345678")
	dbname := getEnv("DB_NAME", "car_detection")

	psqlInfo := fmt.Sprintf("host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
		host, port, user, password, dbname)

	var err error
	db, err = sql.Open("postgres", psqlInfo)
	if err != nil {
		log.Fatalf("Erro ao conectar ao banco de dados: %v\n", err)
	}
	defer db.Close()

	// Testar conexão
	err = db.Ping()
	if err != nil {
		log.Fatalf("Erro ao fazer ping no banco de dados: %v\n", err)
	}

	fmt.Println("✅ Conectado ao PostgreSQL com sucesso!")

	// Configurar pool de conexões
	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)

	// Set up router
	r := mux.NewRouter()

	// Adicionar middleware CORS
	r.Use(enableCORS)

	r.HandleFunc("/health", healthHandler).Methods("GET")
	r.HandleFunc("/data", getDataHandler).Methods("GET")
	r.HandleFunc("/data/{laneId}", getLaneDataHandler).Methods("GET")
	r.HandleFunc("/cache/clear", clearCacheHandler).Methods("POST")

	fmt.Println("🚀 Server is running on http://192.168.0.3:8080")
	fmt.Println("📊 Dashboard endpoint: http://192.168.0.3:8080/data")
	fmt.Println("📊 Specific lane endpoint: http://192.168.0.3:8080/data/{laneId}")
	fmt.Println("❤️ Health check: http://192.168.0.3:8080/health")

	log.Fatal(http.ListenAndServe("0.0.0.0:8080", r))
}

// Função auxiliar para pegar variáveis de ambiente com valor padrão
func getEnv(key, defaultValue string) string {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}
	return value
}

// Health check handler
func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	// Testar conexão com banco
	err := db.Ping()
	status := "ok"
	message := "API is running and database connected"

	if err != nil {
		status = "error"
		message = fmt.Sprintf("Database connection error: %v", err)
	}

	response := map[string]string{
		"status":  status,
		"message": message,
		"version": "2.0 - PostgreSQL Multi-lane support",
	}
	json.NewEncoder(w).Encode(response)
}

// Handler para buscar dados de todas as lanes (padrão lane_1)
func getDataHandler(w http.ResponseWriter, r *http.Request) {
	// Por padrão, buscar dados da lane_1
	getLaneData(w, r, "lane_1")
}

// Handler para buscar dados de uma lane específica
func getLaneDataHandler(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	laneId := vars["laneId"]

	if laneId == "" {
		http.Error(w, "Lane ID is required", http.StatusBadRequest)
		return
	}

	getLaneData(w, r, laneId)
}

// Função principal para buscar dados de uma lane
func getLaneData(w http.ResponseWriter, r *http.Request, laneId string) {
	ctx := context.Background()
	validLanes := []string{"lane_1", "lane_2", "lane_3", "lane_4"}
	isValid := false
	for _, lane := range validLanes {
		if laneId == lane {
			isValid = true
			break
		}
	}
	if !isValid {
		http.Error(w, fmt.Sprintf("Invalid lane_id: %s", laneId), http.StatusBadRequest)
		return
	}

	// Check cache first
	cacheMutex.RLock()
	if cached, exists := dataCache[laneId]; exists {
		if time.Since(cached.Timestamp) < cacheDuration {
			cacheMutex.RUnlock()
			log.Printf("📦 Serving cached data for lane %s (age: %.1fs)",
				laneId, time.Since(cached.Timestamp).Seconds())
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("X-Cache", "HIT")
			json.NewEncoder(w).Encode(cached.Data)
			return
		}
	}
	cacheMutex.RUnlock()

	log.Printf("🔄 Fetching fresh data for lane %s", laneId)

	// Query para buscar os últimos 100 registros da lane específica
	query := `
		SELECT id, timestamp, current_cars, rolling_average, total_count, lane_id
		FROM veiculos
		WHERE lane_id = $1
		ORDER BY timestamp DESC
		LIMIT 100
	`

	rows, err := db.QueryContext(ctx, query, laneId)
	if err != nil {
		if pqErr, ok := err.(*pq.Error); ok {
			log.Printf("PostgreSQL error: Code=%s, Message=%s", pqErr.Code, pqErr.Message)
		}
		log.Printf("Erro ao executar query para lane %s: %v", laneId, err)
		http.Error(w, fmt.Sprintf("Failed to retrieve data from database for lane %s", laneId), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var result []CarDataEntry

	for rows.Next() {
		var entry CarDataEntry
		var timestamp sql.NullTime
		var laneIDNull sql.NullString

		err := rows.Scan(
			&entry.ID,
			&timestamp,
			&entry.CurrentCars,
			&entry.RollingAverage,
			&entry.TotalCount,
			&laneIDNull,
		)

		if err != nil {
			log.Printf("Erro ao fazer scan da linha: %v", err)
			continue
		}

		// Converter timestamp para string
		if timestamp.Valid {
			entry.Timestamp = timestamp.Time.Format("2006-01-02 15:04:05")
		}

		// Garantir que o lane_id está definido
		if laneIDNull.Valid {
			entry.LaneID = laneIDNull.String
		} else {
			entry.LaneID = laneId
		}

		result = append(result, entry)
	}

	// Verificar se houve erro ao iterar pelas linhas
	if err = rows.Err(); err != nil {
		log.Printf("Erro ao iterar pelas linhas: %v", err)
		http.Error(w, "Error processing database results", http.StatusInternalServerError)
		return
	}

	// Se não houver dados, retornar array vazio
	if len(result) == 0 {
		log.Printf("Nenhum dado encontrado para lane %s", laneId)
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode([]CarDataEntry{})
		return
	}

	// Log para debug
	log.Printf("Retrieved %d records from database for lane %s", len(result), laneId)

	// Update cache
	cacheMutex.Lock()
	dataCache[laneId] = CacheEntry{
		Data:      result,
		Timestamp: time.Now(),
		LaneID:    laneId,
	}
	cacheMutex.Unlock()

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Cache", "MISS")
	if err := json.NewEncoder(w).Encode(result); err != nil {
		log.Printf("JSON encoding error: %v", err)
		http.Error(w, "Failed to encode response", http.StatusInternalServerError)
		return
	}
}

// Handler to clear cache (useful for testing)
func clearCacheHandler(w http.ResponseWriter, r *http.Request) {
	cacheMutex.Lock()
	cleared := len(dataCache)
	dataCache = make(map[string]CacheEntry)
	cacheMutex.Unlock()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "ok",
		"message": fmt.Sprintf("Cache cleared: %d entries removed", cleared),
	})
	log.Printf("🗑️ Cache cleared: %d entries", cleared)
}
