package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"

	firebase "firebase.google.com/go/v4" // ✅ Missing in your imports
	"firebase.google.com/go/v4/db"       // ✅ Needed to use db.Client
	"github.com/gorilla/mux"             // ✅ Needed for routing
	"google.golang.org/api/option"
)

var client *db.Client

const firebaseURL = "https://projetedb-2224f-default-rtdb.firebaseio.com/"

// Replace this with your actual JSON key file path
const keyPath = "dbKey.json"

type carData struct {
	CurrentCars    float64 `json:"current_cars"`
	RollingAverage float64 `json:"rolling_average"`
	TotalCount     float64 `json:"total_count"`
	TimeStamp      float64 `json:"timestamp"`
}

func main() {
	ctx := context.Background() // ✅ FIXED: you forgot the `:=`

	conf := &firebase.Config{
		DatabaseURL: firebaseURL,
	}

	// ✅ FIXED: format string usage — don't use fmt.Sprfloat64 like this
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
	r.HandleFunc("/data", getDataHandler).Methods("GET")

	fmt.Println("🚀 Server is running on http://localhost:8080")
	log.Fatal(http.ListenAndServe(":8080", r))
}

// Handler to get data from Firebase
func getDataHandler(w http.ResponseWriter, r *http.Request) {
	ctx := context.Background()

	ref := client.NewRef("car_detection")

	// captura as últimas 1 sessões
	var raw map[string]map[string]carData
	err := ref.OrderByKey().LimitToLast(1).Get(ctx, &raw)
	if err != nil {
		http.Error(w, "Failed to retrieve last session", http.StatusInternalServerError)
		log.Println("Firebase get error:", err)
		return
	}

	// como só pegamos 1 sessão, extrai ela
	var result []carData
	for _, timestamps := range raw {
		for _, entry := range timestamps {
			result = append(result, entry)
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}
