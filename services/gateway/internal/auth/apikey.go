// MODULE: atlas-gateway
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// CONTRACT: ErrorEnvelope codes AUTH_INVALID_KEY, AUTH_MISSING_KEY
package auth

import (
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/atlas-ai/services/gateway/internal/config"
)

type ErrorEnvelope struct {
	TraceID     string `json:"trace_id"`
	Service     string `json:"service"`
	Code        string `json:"code"`
	Retryable   bool   `json:"retryable"`
	HTTPStatus  int    `json:"http_status"`
	Message     string `json:"message"`
	TimestampMs int64  `json:"timestamp_ms"`
}

type APIKeyValidator struct {
	customers map[string]config.CustomerConfig
}

func NewAPIKeyValidator(customers map[string]config.CustomerConfig) *APIKeyValidator {
	return &APIKeyValidator{customers: customers}
}

func (v *APIKeyValidator) Validate(key string) (*config.CustomerConfig, error) {
	if key == "" {
		return nil, fmt.Errorf("AUTH_MISSING_KEY")
	}
	for i := range v.customers {
		cfg := v.customers[i]
		if subtle.ConstantTimeCompare([]byte(cfg.APIKey), []byte(key)) == 1 {
			return &cfg, nil
		}
	}
	return nil, fmt.Errorf("AUTH_INVALID_KEY")
}

func WriteErrorEnvelope(w http.ResponseWriter, traceID, code string, retryable bool, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	env := ErrorEnvelope{
		TraceID:     traceID,
		Service:     "gateway",
		Code:        code,
		Retryable:   retryable,
		HTTPStatus:  status,
		Message:     message,
		TimestampMs: time.Now().UnixMilli(),
	}
	if err := json.NewEncoder(w).Encode(env); err != nil {
		http.Error(w, "internal error", http.StatusInternalServerError)
	}
}
