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
	"math"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/atlas-ai/services/ingestion/internal/adapter"
	"github.com/atlas-ai/services/ingestion/internal/config"
	"github.com/atlas-ai/services/ingestion/internal/ipc"
	"github.com/atlas-ai/services/ingestion/internal/metrics"
)

// ============================================================================
// Health Check Types
// ============================================================================

type Checker interface {
	Name() string
	Check(ctx context.Context) error
}

type CheckResult struct {
	Status  string `json:"status"`
	Message string `json:"message,omitempty"`
}

type HealthResponse struct {
	Status    string                 `json:"status"`
	Checks    map[string]CheckResult `json:"checks"`
	Timestamp string                 `json:"timestamp"`
	Service   string                 `json:"service"`
	Version   string                 `json:"version"`
}

type adapterChecker struct {
	mu       sync.RWMutex
	adapters []adapter.ExchangeAdapter
}

func (c *adapterChecker) Name() string { return "websocket-adapters" }

func (c *adapterChecker) SetAdapters(adapters []adapter.ExchangeAdapter) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.adapters = adapters
}

func (c *adapterChecker) Check(ctx context.Context) error {
	c.mu.RLock()
	adapters := c.adapters
	c.mu.RUnlock()
	for _, a := range adapters {
		if !a.IsConnected() {
			return fmt.Errorf("adapter %q not connected", a.Name())
		}
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
// Adapter Factory
// ============================================================================

func createAdapter(cfg config.ExchangeConfig, common config.Config) adapter.ExchangeAdapter {
	adapterCfg := adapter.Config{
		APIKey:       cfg.APIKey,
		APISecret:    cfg.APISecret,
		Testnet:      cfg.Testnet,
		Symbols:      cfg.Symbols,
		MaxReconnect: common.ReconnectMaxRetries,
		BaseDelayMs:  common.ReconnectBaseDelayMs,
	}
	switch cfg.Name {
	case "bybit":
		return adapter.NewBybitAdapter(adapterCfg)
	case "okx":
		return adapter.NewOKXAdapter(adapterCfg)
	case "aster":
		return adapter.NewAsterAdapter(adapterCfg)
	case "hyperliquid":
		return adapter.NewHyperliquidAdapter(adapterCfg)
	default:
		slog.Warn("unknown exchange adapter", "name", cfg.Name)
		return nil
	}
}

// ============================================================================
// Exchange Worker
// ============================================================================

func runExchangeWorker(ctx context.Context, a adapter.ExchangeAdapter, symbols []string, writer *ipc.Writer, baseDelay time.Duration, maxRetries int) {
	name := a.Name()
	slog.InfoContext(ctx, "worker_starting", "exchange", name)

	for {
		select {
		case <-ctx.Done():
			slog.InfoContext(ctx, "worker_stopping", "exchange", name)
			return
		default:
		}

		// Connect
		connCtx, connCancel := context.WithTimeout(ctx, 10*time.Second)
		err := a.Connect(connCtx)
		connCancel()
		if err != nil {
			slog.ErrorContext(ctx, "connect_failed", "exchange", name, "error", err)
			if !reconnectWait(ctx, baseDelay, 1) {
				return
			}
			continue
		}

		// Subscribe
		subCtx, subCancel := context.WithTimeout(ctx, 10*time.Second)
		err = a.Subscribe(subCtx, symbols)
		subCancel()
		if err != nil {
			slog.ErrorContext(ctx, "subscribe_failed", "exchange", name, "error", err)
			a.Close()
			if !reconnectWait(ctx, baseDelay, 1) {
				return
			}
			continue
		}

		// Start heartbeat
		hbCtx, hbCancel := context.WithCancel(ctx)
		go heartbeatLoop(hbCtx, a)

		// Read loop
		readErr := readLoop(ctx, a, writer)

		hbCancel()
		a.Close()

		if ctx.Err() != nil {
			return // graceful shutdown
		}

		slog.WarnContext(ctx, "read_loop_exited", "exchange", name, "error", readErr)

		// Reconnect with exponential backoff
		reconnected := false
		for attempt := 1; attempt <= maxRetries; attempt++ {
			if ctx.Err() != nil {
				return
			}
			delay := calcBackoff(baseDelay, attempt)
			slog.InfoContext(ctx, "reconnecting", "exchange", name, "attempt", attempt, "delay_ms", delay.Milliseconds())
			metrics.ReconnectionAttempts.WithLabelValues(name).Inc()
			if !reconnectWait(ctx, delay, 1) {
				return
			}
			connCtx2, cancel2 := context.WithTimeout(ctx, 10*time.Second)
			err = a.Connect(connCtx2)
			cancel2()
			if err == nil {
				subCtx2, cancel3 := context.WithTimeout(ctx, 10*time.Second)
				err = a.Subscribe(subCtx2, symbols)
				cancel3()
				if err == nil {
					reconnected = true
					break
				}
				a.Close()
			}
		}
		if !reconnected {
			slog.ErrorContext(ctx, "max_reconnect_exceeded", "exchange", name)
			metrics.ConnectionState.Set(3) // circuit_broken
			return
		}
	}
}

func readLoop(ctx context.Context, a adapter.ExchangeAdapter, writer *ipc.Writer) error {
	name := a.Name()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		frame, traceID, err := a.ReadFrame(ctx)
		if err != nil {
			return err
		}

		// Serialize with trace and write to IPC
		serialized := ipc.SerializeFrameTraced(frame, traceID)
		if err := writer.WriteRaw(serialized); err != nil {
			slog.ErrorContext(ctx, "ipc_write_failed", "exchange", name, "error", err)
		}
	}
}

func heartbeatLoop(ctx context.Context, a adapter.ExchangeAdapter) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
			if err := a.Ping(pingCtx); err != nil {
				slog.WarnContext(ctx, "heartbeat_failed", "exchange", a.Name(), "error", err)
				metrics.HeartbeatFailures.Inc()
			}
			cancel()
		}
	}
}

func reconnectWait(ctx context.Context, delay time.Duration, multiplier int) bool {
	timer := time.NewTimer(delay * time.Duration(multiplier))
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}

func calcBackoff(base time.Duration, attempt int) time.Duration {
	mult := math.Pow(2, float64(attempt-1))
	d := time.Duration(float64(base) * mult)
	max := 30 * time.Second
	if d > max {
		return max
	}
	return d
}

// ============================================================================
// Main
// ============================================================================

func main() {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Register metrics FIRST
	metrics.Register()

	serviceName := "ingestion"
	version := os.Getenv("ATLAS_SERVICE_VERSION")
	if version == "" {
		version = "dev"
	}

	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		slog.ErrorContext(ctx, "config_load_failed", "error", err)
		os.Exit(1)
	}

	slog.InfoContext(ctx, "starting", "service", serviceName, "version", version,
		"exchanges", len(cfg.Exchanges), "ipc_socket", cfg.IPCSocketPath)

	// Scaffold mode: health only, no WS
	if os.Getenv("ATLAS_SCAFFOLD_MODE") == "1" {
		slog.WarnContext(ctx, "SCAFFOLD MODE - no WS connections")
		checker := &adapterChecker{}
		mux := http.NewServeMux()
		mux.HandleFunc("/health/live", liveHandler(serviceName, version))
		mux.HandleFunc("/health/ready", readyHandler(serviceName, version, []Checker{checker}))
		server := &http.Server{
			Addr:         ":" + cfg.MetricsPort,
			Handler:      mux,
			ReadTimeout:  5 * time.Second,
			WriteTimeout: 10 * time.Second,
			IdleTimeout:  120 * time.Second,
		}
		go func() {
			if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
				slog.ErrorContext(ctx, "http_server_error", "error", err)
				cancel()
			}
		}()
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer shutdownCancel()
		server.Shutdown(shutdownCtx)
		os.Exit(0)
	}

	// Production mode
	// Create IPC writer
	writer := ipc.NewWriter(cfg.IPCSocketPath)
	if err := writer.Connect(); err != nil {
		slog.ErrorContext(ctx, "ipc_connect_failed", "error", err)
		os.Exit(1)
	}
	defer writer.Close()

	// Create adapters
	var adapters []adapter.ExchangeAdapter
	for _, exCfg := range cfg.Exchanges {
		a := createAdapter(exCfg, *cfg)
		if a == nil {
			slog.WarnContext(ctx, "skipping unknown exchange", "name", exCfg.Name)
			continue
		}
		adapters = append(adapters, a)
	}

	if len(adapters) == 0 {
		slog.ErrorContext(ctx, "no valid adapters configured")
		os.Exit(1)
	}

	// Health checker
	checker := &adapterChecker{}
	checker.SetAdapters(adapters)

	// Health + Metrics HTTP server
	mux := http.NewServeMux()
	mux.HandleFunc("/health/live", liveHandler(serviceName, version))
	mux.HandleFunc("/health/ready", readyHandler(serviceName, version, []Checker{checker}))
	mux.Handle("/metrics", metricsHTTPHandler())
	server := &http.Server{
		Addr:         ":" + cfg.MetricsPort,
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  120 * time.Second,
	}
	go func() {
		slog.InfoContext(ctx, "health_metrics_server", "port", cfg.MetricsPort)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.ErrorContext(ctx, "http_server_error", "error", err)
		}
	}()

	// Start exchange workers
	var wg sync.WaitGroup
	for i, a := range adapters {
		wg.Add(1)
		go func(idx int, ad adapter.ExchangeAdapter) {
			defer wg.Done()
			exCfg := cfg.Exchanges[idx]
			runExchangeWorker(ctx, ad, exCfg.Symbols, writer,
				cfg.ReconnectBaseDelay(), cfg.ReconnectMaxRetries)
		}(i, a)
	}

	slog.InfoContext(ctx, "production_mode_active", "workers", len(adapters))

	// Wait for shutdown signal
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	sig := <-sigCh
	slog.InfoContext(ctx, "shutdown_signal", "signal", sig.String())

	// Graceful shutdown
	cancel() // cancel context → stops all workers

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer shutdownCancel()

	// Close all adapters
	for _, a := range adapters {
		if err := a.Close(); err != nil {
			slog.ErrorContext(ctx, "adapter_close_error", "exchange", a.Name(), "error", err)
		}
	}

	// Shutdown HTTP server
	server.Shutdown(shutdownCtx)

	// Wait for workers to finish
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		slog.InfoContext(ctx, "all_workers_stopped")
	case <-time.After(10 * time.Second):
		slog.WarnContext(ctx, "worker_shutdown_timeout")
	}

	slog.InfoContext(ctx, "stopped")
}

// metricsHTTPHandler returns Prometheus metrics in text format.
func metricsHTTPHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Use prometheus default handler
		http.DefaultServeMux.ServeHTTP(w, r)
	})
}
