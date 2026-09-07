// MODULE: atlas-gateway
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// CONTRACT: Per-customer auth, WS feed, health, metrics
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/atlas-ai/services/gateway/internal/auth"
	"github.com/atlas-ai/services/gateway/internal/config"
	"github.com/atlas-ai/services/gateway/internal/feed"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config_load_failed", "error", err)
		os.Exit(1)
	}

	validator := auth.NewAPIKeyValidator(cfg.APIKeys)
	hub := feed.NewHub()
	go hub.Run()

	mux := http.NewServeMux()

	// WebSocket stream endpoint
	streamHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		customer := auth.GetCustomer(r.Context())
		if customer == nil {
			tid := auth.GetTraceID(r.Context())
			auth.WriteErrorEnvelope(w, tid, "INT_INVARIANT_BROKEN", false, http.StatusInternalServerError, "customer missing from context")
			return
		}
		client := feed.NewClient(*customer, hub)
		if err := client.ServeWS(w, r); err != nil {
			slog.Warn("client_disconnected", "client_id", client.ID, "error", err)
		}
	})
	mux.Handle("/v1/stream", auth.AuthMiddleware(validator)(streamHandler))

	// Health endpoints
	mux.HandleFunc("/health/live", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/health/ready", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"status":  "ok",
			"clients": hub.ClientCount(),
		})
	})

	// Metrics
	mux.Handle("/metrics", promhttp.Handler())

	server := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Port),
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	// Graceful shutdown
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
		sig := <-sigCh
		slog.Info("shutdown_signal", "signal", sig.String())
		ctx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownTimeout)
		defer cancel()
		hub.Stop()
		if err := server.Shutdown(ctx); err != nil {
			slog.Error("shutdown_error", "error", err)
		}
	}()

	slog.Info("gateway_starting", "port", cfg.Port, "customers", len(cfg.APIKeys))
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		slog.Error("listen_error", "error", err)
		os.Exit(1)
	}
	slog.Info("gateway_stopped")
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		slog.Error("json_encode_error", "error", err)
	}
}
