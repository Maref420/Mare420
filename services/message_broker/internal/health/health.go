// MODULE: atlas-message-broker
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// Health endpoints per governance go-policy.yaml:
//   - graceful_shutdown_required: true
//   - race_safety_required: true
//   - Separate liveness vs readiness probes
package health

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
	"time"
)

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
	Checks    map[string]CheckResult `json:"checks,omitempty"`
	Timestamp string                 `json:"timestamp"`
	Service   string                 `json:"service"`
	Version   string                 `json:"version"`
}

// Server manages liveness and readiness probes.
type Server struct {
	mu           sync.RWMutex
	service      string
	version      string
	checkers     []Checker
	checkTimeout time.Duration
}

// NewServer creates a health server with optional dependency checkers.
func NewServer(service, version string, checkers ...Checker) *Server {
	return &Server{
		service:      service,
		version:      version,
		checkers:     checkers,
		checkTimeout: 3 * time.Second,
	}
}

// LiveHandler returns 200 as long as the process is running.
func (s *Server) LiveHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		writeJSON(w, http.StatusOK, HealthResponse{
			Status:    "ok",
			Timestamp: time.Now().UTC().Format(time.RFC3339),
			Service:   s.service,
			Version:   s.version,
		})
	}
}

// ReadyHandler returns 200 only if all checkers pass.
func (s *Server) ReadyHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		s.mu.RLock()
		checkers := make([]Checker, len(s.checkers))
		copy(checkers, s.checkers)
		s.mu.RUnlock()

		checks := make(map[string]CheckResult, len(checkers))
		var mu sync.Mutex
		var wg sync.WaitGroup
		anyFailed := false

		for _, c := range checkers {
			wg.Add(1)
			go func(chk Checker) {
				defer wg.Done()
				ctx, cancel := context.WithTimeout(r.Context(), s.checkTimeout)
				defer cancel()

				if err := chk.Check(ctx); err != nil {
					msg := err.Error()
					if ctx.Err() == context.DeadlineExceeded {
						msg = "check timeout"
					} else if ctx.Err() == context.Canceled {
						msg = "check cancelled"
					}
					mu.Lock()
					checks[chk.Name()] = CheckResult{Status: "fail", Message: msg}
					anyFailed = true
					mu.Unlock()
					slog.WarnContext(ctx, "health check failed", "checker", chk.Name(), "error", err)
				} else {
					mu.Lock()
					checks[chk.Name()] = CheckResult{Status: "ok"}
					mu.Unlock()
				}
			}(c)
		}
		wg.Wait()

		status := "ok"
		code := http.StatusOK
		if anyFailed {
			status = "fail"
			code = http.StatusServiceUnavailable
		}

		writeJSON(w, code, HealthResponse{
			Status:    status,
			Checks:    checks,
			Timestamp: time.Now().UTC().Format(time.RFC3339),
			Service:   s.service,
			Version:   s.version,
		})
	}
}

// RegisterRoutes mounts /health/live and /health/ready on the mux.
// Backward compatible: also mounts legacy /health → live handler.
func (s *Server) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/health/live", s.LiveHandler())
	mux.HandleFunc("/health/ready", s.ReadyHandler())
	mux.HandleFunc("/health", s.LiveHandler()) // backward compat
}

func writeJSON(w http.ResponseWriter, statusCode int, resp HealthResponse) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		slog.Error("failed to encode health response", "error", err)
	}
}

// Handler is kept for backward compatibility but deprecated.
// Use NewServer + RegisterRoutes instead.
func Handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		resp := HealthResponse{
			Status:    "ok",
			Timestamp: time.Now().UTC().Format(time.RFC3339),
			Service:   "message-broker",
			Version:   "dev",
		}
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			slog.Error("failed to encode health response", "error", err)
		}
		_ = fmt.Sprintf // suppress unused import
	}
}
