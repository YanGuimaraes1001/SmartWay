package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"

	firebase "firebase.google.com/go/v4"
	"firebase.google.com/go/v4/db"
	"github.com/gorilla/mux"
	"google.golang.org/api/option"
)

var client *db.Client

const firebaseURL = "https://projetedb-2224f-default-rtdb.firebaseio.com/"
const keyPath = "firebaseKey.json"

type carData struct {
	CurrentCars    float64 `json:"current_cars"`
	RollingAverage float64 `json:"rolling_average"`
	TotalCount     float64 `json:"total_count"`
	TimeStamp      float64 `json:"timestamp"`
}

// Middleware para habilitar CORS
func enableCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Permitir origens específicas (ou usar * para desenvolvimento)
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
	ctx := context.Background()

	conf := &firebase.Config{
		DatabaseURL: firebaseURL,
	}

	opt := option.WithCredentialsFile(keyPath)

	app, err := firebase.NewApp(ctx, conf, opt)
	if err != nil {
		log.Fatalf("error initializing app: %v\n", err)
	}

	// Connect to Firebase Realtime Database
	client, err = app.Database(ctx)
	if err != nil {
		log.Fatalf("error initializing database client: %v\n", err)
	}

	// Set up router
	r := mux.NewRouter()

	// Adicionar middleware CORS
	r.Use(enableCORS)

	// Adicionar rota para health check
	r.HandleFunc("/health", healthHandler).Methods("GET")
	r.HandleFunc("/data", getDataHandler).Methods("GET")

	fmt.Println("🚀 Server is running on http://localhost:8080")
	fmt.Println("📊 Dashboard endpoint: http://localhost:8080/data")
	fmt.Println("❤️  Health check: http://localhost:8080/health")

	log.Fatal(http.ListenAndServe(":8080", r))
}

// Health check handler
func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	response := map[string]string{
		"status":  "ok",
		"message": "API is running",
	}
	json.NewEncoder(w).Encode(response)
}

// Handler to get data from Firebase
func getDataHandler(w http.ResponseWriter, r *http.Request) {
	ctx := context.Background()

	ref := client.NewRef("car_detection")

	// Pegar mais dados para ter um histórico melhor (últimas 3 sessões)
	var raw map[string]map[string]carData
	err := ref.OrderByKey().LimitToLast(3).Get(ctx, &raw)
	if err != nil {
		log.Printf("Firebase get error: %v", err)
		http.Error(w, "Failed to retrieve data from Firebase", http.StatusInternalServerError)
		return
	}

	// Se não houver dados, retornar array vazio
	if len(raw) == 0 {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode([]carData{})
		return
	}

	// Extrair todos os dados e organizá-los
	var result []carData
	for _, timestamps := range raw {
		for _, entry := range timestamps {
			result = append(result, entry)
		}
	}

	// Log para debug
	log.Printf("Retrieved %d records from Firebase", len(result))

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(result); err != nil {
		log.Printf("JSON encoding error: %v", err)
		http.Error(w, "Failed to encode response", http.StatusInternalServerError)
		return
	}
}
