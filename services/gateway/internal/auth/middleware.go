// MODULE: atlas-gateway
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// WARNING: No panics on request path. Context propagation mandatory.
package auth

import (
	"context"
	"crypto/rand"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/atlas-ai/services/gateway/internal/config"
)

type ctxKey string

const (
	traceIDKey  ctxKey = "trace_id"
	customerKey ctxKey = "customer"
)

func generateTraceID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "00000000-0000-4000-8000-000000000000"
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

func AuthMiddleware(v *APIKeyValidator) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			tid := generateTraceID()
			ctx := context.WithValue(r.Context(), traceIDKey, tid)

			key := r.Header.Get("X-API-Key")
			if key == "" {
				key = r.URL.Query().Get("api_key")
			}

			customer, err := v.Validate(key)
			if err != nil {
				code := err.Error()
				WriteErrorEnvelope(w, tid, code, false, http.StatusUnauthorized, "missing or invalid api key")
				slog.Warn("auth_failed", "trace_id", tid, "duration_ms", time.Since(start).Milliseconds())
				return
			}

			ctx = context.WithValue(ctx, customerKey, customer)
			next.ServeHTTP(w, r.WithContext(ctx))
			slog.Info("request_served", "trace_id", tid, "customer", customer.Name, "duration_ms", time.Since(start).Milliseconds())
		})
	}
}

func GetTraceID(ctx context.Context) string {
	if val, ok := ctx.Value(traceIDKey).(string); ok {
		return val
	}
	return "unknown"
}

func GetCustomer(ctx context.Context) *config.CustomerConfig {
	if val, ok := ctx.Value(customerKey).(*config.CustomerConfig); ok {
		return val
	}
	return nil
}
