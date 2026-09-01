// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// ADR: docs/decisions/007a-trace-id-propagation-addendum.md
// EXCHANGE: Bybit v5 Public WebSocket
// DOCS: https://bybit-exchange.github.io/docs/v5/ws/connect
// CHECKLIST: CR-P0-004 v3 Sections A-H
// RATE LIMITS: 10 ops/sec subscribe, 50 msg/s outbound (D1)
// RECONNECT: State recovery with automatic re-subscribe (D4)
// WARNING: Raw frames only. No parsing, no normalization.

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
	bybitTestnetWS      = "wss://testnet.bybit.com/v5/public"
	bybitMainnetWS      = "wss://stream.bybit.com/v5/public"
	bybitSubscribeRate  = 10.0  // ops/sec
	bybitSubscribeBurst = 5.0   // burst capacity
)

// BybitAdapter implements ExchangeAdapter for Bybit v5 public WebSocket.
type BybitAdapter struct {
	cfg       Config
	conn      *websocket.Conn
	mu        sync.Mutex
	connected bool
	tracer    *TraceGenerator
	limiter   *RateLimiter

	// D4: Subscription state for reconnect recovery
	lastSymbols []string
}

func NewBybitAdapter(cfg Config) *BybitAdapter {
	return &BybitAdapter{
		cfg:     cfg,
		tracer:  NewTraceGenerator("bybit"),
		limiter: NewRateLimiter(bybitSubscribeBurst, bybitSubscribeRate),
	}
}

func (b *BybitAdapter) Name() string { return "bybit" }

func (b *BybitAdapter) Connect(ctx context.Context) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	wsURL := bybitMainnetWS
	if b.cfg.Testnet {
		wsURL = bybitTestnetWS
	}

	conn, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		metrics.ErrorEvents.WithLabelValues("bybit_connect").Inc()
		slog.Error("bybit connect failed", "url", wsURL, "error", err)
		return fmt.Errorf("bybit dial failed: %w", err)
	}

	b.conn = conn
	b.connected = true
	metrics.ConnectionState.Set(1)
	slog.Info("bybit connected", "url", wsURL, "testnet", b.cfg.Testnet)

	// D4: Re-subscribe if we have previous state
	if len(b.lastSymbols) > 0 {
		slog.Info("bybit re-subscribing after reconnect", "symbols", b.lastSymbols)
		metrics.ReconnectionAttempts.WithLabelValues("resubscribe").Inc()
		if err := b.subscribeLocked(ctx, b.lastSymbols); err != nil {
			slog.Error("bybit re-subscribe failed", "error", err)
			// Non-fatal: connection is alive, just missing subscriptions
		}
	}

	return nil
}

func (b *BybitAdapter) Subscribe(ctx context.Context, symbols []string) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	if !b.connected || b.conn == nil {
		return fmt.Errorf("bybit not connected")
	}

	// D4: Cache symbols for reconnect recovery
	b.lastSymbols = make([]string, len(symbols))
	copy(b.lastSymbols, symbols)

	return b.subscribeLocked(ctx, symbols)
}

// subscribeLocked performs subscription with rate limiting (D1).
// Caller MUST hold b.mu.
func (b *BybitAdapter) subscribeLocked(ctx context.Context, symbols []string) error {
	// D1: Rate limit check
	if !b.limiter.Allow() {
		metrics.ErrorEvents.WithLabelValues("bybit_rate_limited").Inc()
		slog.Warn("bybit subscribe rate limited, waiting", "symbols", symbols)
		if err := b.limiter.Wait(ctx); err != nil {
			return fmt.Errorf("rate limiter wait cancelled: %w", err)
		}
	}

	args := make([]string, len(symbols))
	for i, s := range symbols {
		args[i] = fmt.Sprintf(`"tickers.%s"`, s)
	}
	msg := fmt.Sprintf(`{"op":"subscribe","args":[%s]}`, strings.Join(args, ","))

	if err := b.conn.Write(ctx, websocket.MessageText, []byte(msg)); err != nil {
		metrics.ErrorEvents.WithLabelValues("bybit_subscribe").Inc()
		slog.Error("bybit subscribe failed", "symbols", symbols, "error", err)
		return fmt.Errorf("bybit subscribe failed: %w", err)
	}

	slog.Info("bybit subscribed", "symbols", symbols)
	return nil
}

// ReadFrame returns raw frame + trace_id per ADR-007a (H1, H5).
func (b *BybitAdapter) ReadFrame(ctx context.Context) ([]byte, string, error) {
	b.mu.Lock()
	conn := b.conn
	b.mu.Unlock()

	if conn == nil {
		return nil, "", fmt.Errorf("bybit not connected")
	}

	_, data, err := conn.Read(ctx)
	if err != nil {
		metrics.ErrorEvents.WithLabelValues("bybit_read").Inc()
		b.mu.Lock()
		b.connected = false
		metrics.ConnectionState.Set(2) // reconnecting
		b.mu.Unlock()
		return nil, "", fmt.Errorf("bybit read failed: %w", err)
	}

	metrics.FramesReceived.Inc()
	traceID := b.tracer.Generate()

	slog.Debug("bybit frame received", "trace_id", traceID, "size_bytes", len(data))
	return data, traceID, nil
}

func (b *BybitAdapter) Ping(ctx context.Context) error {
	b.mu.Lock()
	conn := b.conn
	b.mu.Unlock()

	if conn == nil {
		return fmt.Errorf("bybit not connected")
	}

	if err := conn.Write(ctx, websocket.MessageText, []byte(`{"op":"ping"}`)); err != nil {
		metrics.HeartbeatFailures.Inc()
		slog.Error("bybit ping failed", "error", err)
		return fmt.Errorf("bybit ping failed: %w", err)
	}
	return nil
}

func (b *BybitAdapter) Close() error {
	b.mu.Lock()
	defer b.mu.Unlock()

	if !b.connected || b.conn == nil {
		return nil
	}
	b.connected = false
	metrics.ConnectionState.Set(0)
	slog.Info("bybit connection closed")
	return b.conn.Close(websocket.StatusNormalClosure, "closing")
}

func (b *BybitAdapter) IsConnected() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.connected
}
