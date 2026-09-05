// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// CONTRACT: IPC binary format v1 (length-prefixed over UDS)
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/atlas-ai/services/ingestion/internal/adapter"
	"github.com/atlas-ai/services/ingestion/internal/metrics"
)

// ============================================================================
// Health Check Types (inline per governance: no cross-module import duplication)
// Contract matches foundation/health/go_health.go exactly.
// ============================================================================

// Checker defines the interface for dependency health checks.
type Checker interface {
	Name() string
	Check(ctx context.Context) error
}

// CheckResult represents the outcome of a single dependency check.
type CheckResult struct {
	Status  string `json:"status"`
	Message string `json:"message,omitempty"`
}

// HealthResponse defines the JSON payload for health endpoints.
type HealthResponse struct {
	Status    string                 `json:"status"`
	Checks    map[string]CheckResult `json:"checks"`
	Timestamp string                 `json:"timestamp"`
	Service   string                 `json:"service"`
	Version   string                 `json:"version"`
}

// ============================================================================
// WebSocket Adapter Checker
// ============================================================================

// adapterChecker implements Checker using ExchangeAdapter.IsConnected().
type adapterChecker struct {
	mu      sync.RWMutex
	adapter adapter.ExchangeAdapter
}

func newAdapterChecker() *adapterChecker {
	return &adapterChecker{}
}

func (c *adapterChecker) Name() string { return "websocket-adapter" }

func (c *adapterChecker) SetAdapter(a adapter.ExchangeAdapter) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.adapter = a
}

func (c *adapterChecker) Check(ctx context.Context) error {
	c.mu.RLock()
	a := c.adapter
	c.mu.RUnlock()

	if a == nil {
		return fmt.Errorf("websocket adapter not initialized")
	}
	if !a.IsConnected() {
		return fmt.Errorf("websocket adapter %q not connected", a.Name())
	}
	return nil
}

// ============================================================================
// Health HTTP Handlers
// ============================================================================

func liveHandler(service, version string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		writeHealthJSON(w, http.StatusOK, HealthResponse{
			Status:    "ok",
			Timestamp: time.Now().UTC().Format(time.RFC3339),
			Service:   service,
			Version:   version,
		})
	}
}

func readyHandler(service, version string, checkers []Checker) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		checks := make(map[string]CheckResult, len(checkers))
		var mu sync.Mutex
		var wg sync.WaitGroup
		anyFailed := false

		for _, c := range checkers {
			wg.Add(1)
			go func(chk Checker) {
				defer wg.Done()
				ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
				defer cancel()

				if err := chk.Check(ctx); err != nil {
					msg := err.Error()
					if ctx.Err() == context.DeadlineExceeded {
						msg = "check timeout"
					}
					mu.Lock()
					checks[chk.Name()] = CheckResult{Status: "fail", Message: msg}
					anyFailed = true
					mu.Unlock()
				} else {
					mu.Lock()
					checks[chk.Name()] = CheckResult{Status: "ok"}
					mu.Unlock()
				}
			}(c)
		}
		wg.Wait()

		status := "ok"
		httpCode := http.StatusOK
		if anyFailed {
			status = "fail"
			httpCode = http.StatusServiceUnavailable
		}

		writeHealthJSON(w, httpCode, HealthResponse{
			Status:    status,
			Checks:    checks,
			Timestamp: time.Now().UTC().Format(time.RFC3339),
			Service:   service,
			Version:   version,
		})
	}
}

func writeHealthJSON(w http.ResponseWriter, statusCode int, resp HealthResponse) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		slog.Error("failed to encode health response", "error", err)
	}
}

// ============================================================================
// Main
// ============================================================================

func main() {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Register all Prometheus metrics BEFORE any other operation.
	metrics.Register()

	serviceName := "ingestion"
	version := os.Getenv("ATLAS_SERVICE_VERSION")
	if version == "" {
		version = "dev"
	}

	// Scaffold mode: health endpoints available, no WS connection.
	if os.Getenv("ATLAS_SCAFFOLD_MODE") == "1" {
		slog.WarnContext(ctx, "running in SCAFFOLD MODE - no WS connection will be established")

		checker := newAdapterChecker() // adapter is nil → readiness will fail
		mux := http.NewServeMux()
		mux.HandleFunc("/health/live", liveHandler(serviceName, version))
		mux.HandleFunc("/health/ready", readyHandler(serviceName, version, []Checker{checker}))

		server := &http.Server{
			Addr:         ":8080",
			Handler:      mux,
			ReadTimeout:  5 * time.Second,
			WriteTimeout: 10 * time.Second,
			IdleTimeout:  120 * time.Second,
		}

		go func() {
			slog.InfoContext(ctx, "health server starting", "address", server.Addr)
			if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
				slog.ErrorContext(ctx, "http_server_error", "error", err)
				cancel()
			}
		}()

		slog.InfoContext(ctx, "started", "service", serviceName, "port", 8080, "mode", "scaffold")

		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh

		slog.InfoContext(ctx, "shutdown_signal_received")
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer shutdownCancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			slog.ErrorContext(ctx, "shutdown_error", "error", err)
		}
		slog.InfoContext(ctx, "stopped")
		os.Exit(0)
	}

	// Production mode: business logic not yet implemented per ADR-006.
	slog.ErrorContext(ctx, "business logic not yet implemented")
	slog.ErrorContext(ctx, "this binary MUST NOT run in production without completed implementation per ADR-006")
	os.Exit(1)
}
