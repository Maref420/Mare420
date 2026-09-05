// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// ADR: docs/decisions/007a-trace-id-propagation-addendum.md
// EXCHANGE: OKX v5 Public WebSocket (no auth for public channels)
// DOCS: https://www.okx.com/docs-v5/en/#overview-websocket-overview
// CHECKLIST: CR-P0-004 v3 Sections A-H
// RATE LIMITS: 20 subscribe/unsubscribe per 10 seconds (D1)
// RECONNECT: State recovery with automatic re-subscribe (D4)
// WARNING: Raw frames only. No parsing, no normalization.
//          "pong" responses filtered internally (not forwarded).

package adapter

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"

	"github.com/atlas-ai/services/ingestion/internal/metrics"
	"nhooyr.io/websocket"
)

const (
	okxTestnetWS     = "wss://wspap.okx.com:8443/ws/v5/public"
	okxMainnetWS     = "wss://ws.okx.com:8443/ws/v5/public"
	okxSubscribeRate = 2.0   // 20 per 10 sec = 2/sec sustained
	okxSubscribeBurst = 10.0 // burst capacity
)

// OKXAdapter implements ExchangeAdapter for OKX v5 public WebSocket.
type OKXAdapter struct {
	cfg         Config
	conn        *websocket.Conn
	mu          sync.Mutex
	connected   bool
	tracer      *TraceGenerator
	limiter     *RateLimiter
	lastSymbols []string // D4: subscription state for reconnect
}

func NewOKXAdapter(cfg Config) *OKXAdapter {
	return &OKXAdapter{
		cfg:     cfg,
		tracer:  NewTraceGenerator("okx"),
		limiter: NewRateLimiter(okxSubscribeBurst, okxSubscribeRate),
	}
}

func (o *OKXAdapter) Name() string { return "okx" }

func (o *OKXAdapter) Connect(ctx context.Context) error {
	o.mu.Lock()
	defer o.mu.Unlock()

	wsURL := okxMainnetWS
	if o.cfg.Testnet {
		wsURL = okxTestnetWS
	}

	conn, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		metrics.ErrorEvents.WithLabelValues("okx_connect").Inc()
		slog.Error("okx connect failed", "url", wsURL, "error", err)
		return fmt.Errorf("okx dial failed: %w", err)
	}

	o.conn = conn
	o.connected = true
	metrics.ConnectionState.Set(1)
	slog.Info("okx connected", "url", wsURL, "testnet", o.cfg.Testnet)

	// D4: Re-subscribe if we have previous state
	if len(o.lastSymbols) > 0 {
		slog.Info("okx re-subscribing after reconnect", "symbols", o.lastSymbols)
		metrics.ReconnectionAttempts.WithLabelValues("resubscribe").Inc()
		if err := o.subscribeLocked(ctx, o.lastSymbols); err != nil {
			slog.Error("okx re-subscribe failed", "error", err)
		}
	}

	return nil
}

func (o *OKXAdapter) Subscribe(ctx context.Context, symbols []string) error {
	o.mu.Lock()
	defer o.mu.Unlock()

	if !o.connected || o.conn == nil {
		return fmt.Errorf("okx not connected")
	}

	// D4: Cache symbols for reconnect recovery
	o.lastSymbols = make([]string, len(symbols))
	copy(o.lastSymbols, symbols)

	return o.subscribeLocked(ctx, symbols)
}

// subscribeLocked performs subscription with rate limiting (D1).
// OKX v5 format: {"op":"subscribe","args":[{"channel":"tickers","instId":"BTC-USDT"}]}
// Caller MUST hold o.mu.
func (o *OKXAdapter) subscribeLocked(ctx context.Context, symbols []string) error {
	// D1: Rate limit check
	if !o.limiter.Allow() {
		metrics.ErrorEvents.WithLabelValues("okx_rate_limited").Inc()
		slog.Warn("okx subscribe rate limited, waiting", "symbols", symbols)
		if err := o.limiter.Wait(ctx); err != nil {
			return fmt.Errorf("rate limiter wait cancelled: %w", err)
		}
	}

	args := make([]string, len(symbols))
	for i, s := range symbols {
		args[i] = fmt.Sprintf(`{"channel":"tickers","instId":"%s"}`, s)
	}
	msg := fmt.Sprintf(`{"op":"subscribe","args":[%s]}`, strings.Join(args, ","))

	if err := o.conn.Write(ctx, websocket.MessageText, []byte(msg)); err != nil {
		metrics.ErrorEvents.WithLabelValues("okx_subscribe").Inc()
		slog.Error("okx subscribe failed", "symbols", symbols, "error", err)
		return fmt.Errorf("okx subscribe failed: %w", err)
	}

	slog.Info("okx subscribed", "symbols", symbols)
	return nil
}

// ReadFrame returns raw frame + trace_id per ADR-007a (H1, H5).
// Filters out OKX "pong" responses transparently.
func (o *OKXAdapter) ReadFrame(ctx context.Context) ([]byte, string, error) {
	o.mu.Lock()
	conn := o.conn
	o.mu.Unlock()

	if conn == nil {
		return nil, "", fmt.Errorf("okx not connected")
	}

	for {
		_, data, err := conn.Read(ctx)
		if err != nil {
			metrics.ErrorEvents.WithLabelValues("okx_read").Inc()
			o.mu.Lock()
			o.connected = false
			metrics.ConnectionState.Set(2) // reconnecting
			o.mu.Unlock()
			return nil, "", fmt.Errorf("okx read failed: %w", err)
		}

		// Filter pong responses (OKX sends text "pong" as heartbeat reply)
		if isPong(data) {
			continue
		}

		metrics.FramesReceived.Inc()
		traceID := o.tracer.Generate()

		slog.Debug("okx frame received", "trace_id", traceID, "size_bytes", len(data))
		return data, traceID, nil
	}
}

// Ping sends OKX v5 text-frame ping (NOT JSON).
// OKX spec: send "ping" text, server replies "pong" text.
func (o *OKXAdapter) Ping(ctx context.Context) error {
	o.mu.Lock()
	conn := o.conn
	o.mu.Unlock()

	if conn == nil {
		return fmt.Errorf("okx not connected")
	}

	// OKX uses plain text "ping", not JSON {"op":"ping"}
	if err := conn.Write(ctx, websocket.MessageText, []byte("ping")); err != nil {
		metrics.HeartbeatFailures.Inc()
		slog.Error("okx ping failed", "error", err)
		return fmt.Errorf("okx ping failed: %w", err)
	}
	return nil
}

func (o *OKXAdapter) Close() error {
	o.mu.Lock()
	defer o.mu.Unlock()

	if !o.connected || o.conn == nil {
		return nil
	}
	o.connected = false
	metrics.ConnectionState.Set(0)
	slog.Info("okx connection closed")
	return o.conn.Close(websocket.StatusNormalClosure, "closing")
}

func (o *OKXAdapter) IsConnected() bool {
	o.mu.Lock()
	defer o.mu.Unlock()
	return o.connected
}

// isPong checks if data is an OKX pong response.
// OKX sends plain text "pong" (not JSON) as heartbeat reply.
func isPong(data []byte) bool {
	return len(data) == 4 && string(data) == "pong"
}
