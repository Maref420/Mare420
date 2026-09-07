// MODULE: atlas-gateway
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// CONTRACT: Per-customer auth, WS feed, IPC bridge, metering, health, metrics
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/atlas-ai/services/gateway/internal/auth"
	"github.com/atlas-ai/services/gateway/internal/config"
	"github.com/atlas-ai/services/gateway/internal/feed"
	"github.com/atlas-ai/services/gateway/internal/metering"
	"github.com/prometheus/client_golang/prometheus"
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

	meter := metering.NewMeter()
	meterDone := make(chan struct{})
	go meter.RunCleanup(30*time.Second, meterDone)
	hub.AttachMeter(meter)

	framesVec := prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "gateway_frames_total", Help: "Total frames processed",
	}, []string{"customer"})
	bytesVec := prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "gateway_bytes_total", Help: "Total bytes processed",
	}, []string{"customer"})
	droppedVec := prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "gateway_dropped_total", Help: "Total frames dropped",
	}, []string{"customer"})
	prometheus.MustRegister(framesVec, bytesVec, droppedVec)

	ipcSocket := os.Getenv("ATLAS_GATEWAY_IPC_SOCKET")
	if ipcSocket == "" {
		ipcSocket = "/app/uds/atlas-ipc.sock"
	}
	if err := os.MkdirAll(filepath.Dir(ipcSocket), 0755); err != nil {
		slog.Error("socket_dir_create_failed", "path", filepath.Dir(ipcSocket), "error", err)
		os.Exit(1)
	}
	if _, statErr := os.Stat(ipcSocket); statErr == nil {
		if err := os.Remove(ipcSocket); err != nil {
			slog.Warn("stale_socket_remove_failed", "socket", ipcSocket, "error", err)
		}
	}
	bridge := feed.NewBridge(hub, meter, ipcSocket, framesVec, bytesVec, droppedVec)

	mux := http.NewServeMux()

	streamHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		customer := auth.GetCustomer(r.Context())
		if customer == nil {
			tid := auth.GetTraceID(r.Context())
			auth.WriteErrorEnvelope(w, tid, "INT_INVARIANT_BROKEN", false, http.StatusInternalServerError, "customer missing from context")
			return
		}
		client := feed.NewClient(*customer, hub)
		client.AttachMeter(meter)
		if err := client.ServeWS(w, r); err != nil {
			slog.Warn("client_disconnected", "client_id", client.ID, "error", err)
		}
	})
	mux.Handle("/v1/stream", auth.AuthMiddleware(validator)(streamHandler))

	usageHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		customer := auth.GetCustomer(r.Context())
		if customer == nil {
			tid := auth.GetTraceID(r.Context())
			auth.WriteErrorEnvelope(w, tid, "AUTH_MISSING_KEY", false, http.StatusUnauthorized, "auth required")
			return
		}
		stats, ok := meter.GetUsage(customer.Name)
		if !ok {
			stats = metering.UsageStats{CustomerID: customer.Name}
		}
		writeJSON(w, http.StatusOK, stats)
	})
	mux.Handle("/v1/usage", auth.AuthMiddleware(validator)(usageHandler))

	mux.HandleFunc("/health/live", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/health/ready", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"status":  "ok",
			"clients": hub.ClientCount(),
		})
	})
	mux.Handle("/metrics", promhttp.Handler())

	server := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Port),
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
		sig := <-sigCh
		slog.Info("shutdown_signal", "signal", sig.String())
		ctx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownTimeout)
		defer cancel()
		bridge.Stop()
		close(meterDone)
		hub.Stop()
		if err := server.Shutdown(ctx); err != nil {
			slog.Error("shutdown_error", "error", err)
		}
	}()

	slog.Info("gateway_starting", "port", cfg.Port, "customers", len(cfg.APIKeys), "ipc_socket", ipcSocket)

	if err := bridge.Start(context.Background()); err != nil {
		slog.Error("bridge_start_failed", "error", err)
		os.Exit(1)
	}

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
