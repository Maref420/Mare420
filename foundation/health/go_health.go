package health

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"sync"
	"time"
)

// Checker defines the interface for dependency health checks.
// Implementations must respect context cancellation and deadline.
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
// Complies with governance structured logging requirements.
type HealthResponse struct {
	Status    string                 `json:"status"`
	Checks    map[string]CheckResult `json:"checks"`
	Timestamp string                 `json:"timestamp"`
	Service   string                 `json:"service"`
	Version   string                 `json:"version"`
}

// HealthServer manages liveness and readiness probes for Go services.
// Thread-safe for concurrent reads (go-policy: race_safety_required).
type HealthServer struct {
	mu           sync.RWMutex
	service      string
	version      string
	checkers     []Checker
	checkTimeout time.Duration
}

// NewHealthServer initializes a HealthServer with optional dependency checkers.
func NewHealthServer(service, version string, checkers ...Checker) *HealthServer {
	return &HealthServer{
		service:      service,
		version:      version,
		checkers:     checkers,
		checkTimeout: 3 * time.Second,
	}
}

// LiveHandler returns an HTTP handler for liveness probes.
// Returns 200 as long as the process is running (no dependency checks).
func (h *HealthServer) LiveHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		h.writeJSON(w, r.Context(), "ok", nil)
	}
}

// ReadyHandler returns an HTTP handler for readiness probes.
// Returns 200 only if all registered checkers pass within timeout.
// Honors parent context deadline (go-policy: graceful_shutdown_required).
func (h *HealthServer) ReadyHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		h.executeReadinessCheck(w, r.Context())
	}
}

// RegisterRoutes mounts health check endpoints on the provided ServeMux.
func (h *HealthServer) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/health/live", h.LiveHandler())
	mux.HandleFunc("/health/ready", h.ReadyHandler())
}

// writeJSON serializes and writes the health response.
// No stack traces or secrets in output (governance I6).
func (h *HealthServer) writeJSON(w http.ResponseWriter, ctx context.Context, status string, checks map[string]CheckResult) {
	resp := HealthResponse{
		Status:    status,
		Checks:    checks,
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Service:   h.service,
		Version:   h.version,
	}
	w.Header().Set("Content-Type", "application/json")
	if status == "ok" {
		w.WriteHeader(http.StatusOK)
	} else {
		w.WriteHeader(http.StatusServiceUnavailable)
	}
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		slog.ErrorContext(ctx, "failed to encode health response", "error", err)
	}
}

// executeReadinessCheck runs all checkers concurrently with bounded timeout.
// Goroutine leak prevention: wg.Wait() ensures all goroutines complete.
// Context propagation: child context honors parent deadline (governance I5).
func (h *HealthServer) executeReadinessCheck(w http.ResponseWriter, parentCtx context.Context) {
	h.mu.RLock()
	checkers := make([]Checker, len(h.checkers))
	copy(checkers, h.checkers)
	h.mu.RUnlock()

	checks := make(map[string]CheckResult, len(checkers))
	var resultsMu sync.Mutex
	var wg sync.WaitGroup
	var anyFailed bool

	for _, c := range checkers {
		wg.Add(1)
		go func(checker Checker) {
			defer wg.Done()

			ctx, cancel := context.WithTimeout(parentCtx, h.checkTimeout)
			defer cancel()

			name := checker.Name()
			if err := checker.Check(ctx); err != nil {
				msg := err.Error()
				if ctx.Err() == context.DeadlineExceeded {
					msg = "check timeout"
				} else if ctx.Err() == context.Canceled {
					msg = "check cancelled"
				}
				resultsMu.Lock()
				checks[name] = CheckResult{Status: "fail", Message: msg}
				anyFailed = true
				resultsMu.Unlock()
				slog.WarnContext(ctx, "health check failed", "checker", name, "error", err)
			} else {
				resultsMu.Lock()
				checks[name] = CheckResult{Status: "ok"}
				resultsMu.Unlock()
			}
		}(c)
	}

	wg.Wait()

	finalStatus := "ok"
	if anyFailed {
		finalStatus = "fail"
	}
	h.writeJSON(w, parentCtx, finalStatus, checks)
}
