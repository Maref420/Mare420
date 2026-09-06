// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// ADR: docs/decisions/007a-trace-id-propagation-addendum.md
// EXCHANGE: Aster DEX Public WebSocket
// CHECKLIST: CR-P0-004 v3 Sections A-H
// RATE LIMITS: 10 ops/sec subscribe (D1)
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
	asterTestnetWS      = "wss://testnet-ws.asterdex.com/ws"
	asterMainnetWS      = "wss://ws.asterdex.com/ws"
	asterSubscribeRate  = 10.0
	asterSubscribeBurst = 5.0
)

type AsterAdapter struct {
	cfg         Config
	conn        *websocket.Conn
	mu          sync.Mutex
	connected   bool
	tracer      *TraceGenerator
	limiter     *RateLimiter
	lastSymbols []string
}

func NewAsterAdapter(cfg Config) *AsterAdapter {
	return &AsterAdapter{
		cfg:     cfg,
		tracer:  NewTraceGenerator("aster"),
		limiter: NewRateLimiter(asterSubscribeBurst, asterSubscribeRate),
	}
}

func (a *AsterAdapter) Name() string { return "aster" }

func (a *AsterAdapter) Connect(ctx context.Context) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	wsURL := asterMainnetWS
	if a.cfg.Testnet {
		wsURL = asterTestnetWS
	}
	slog.InfoContext(ctx, "aster_connecting", "url", wsURL)
	conn, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		metrics.ErrorEvents.WithLabelValues("aster_connect").Inc()
		return fmt.Errorf("aster dial: %w", err)
	}
	a.conn = conn
	a.connected = true
	metrics.ConnectionState.Set(1)
	slog.InfoContext(ctx, "aster_connected")
	return nil
}

func (a *AsterAdapter) Subscribe(ctx context.Context, symbols []string) error {
	a.mu.Lock()
	conn := a.conn
	a.mu.Unlock()
	if conn == nil {
		metrics.ErrorEvents.WithLabelValues("aster_subscribe_not_connected").Inc()
		return fmt.Errorf("aster: not connected")
	}
	if err := a.limiter.Wait(ctx); err != nil {
		metrics.ErrorEvents.WithLabelValues("aster_rate_limited").Inc()
		return fmt.Errorf("aster rate limit: %w", err)
	}
	args := make([]string, 0, len(symbols))
	for _, s := range symbols {
		args = append(args, fmt.Sprintf("ticker.%s", strings.ToUpper(s)))
	}
	msg := fmt.Sprintf(`{"op":"subscribe","args":[%s]}`, quoteArgs(args))
	if err := conn.Write(ctx, websocket.MessageText, []byte(msg)); err != nil {
		metrics.ErrorEvents.WithLabelValues("aster_subscribe").Inc()
		return fmt.Errorf("aster subscribe write: %w", err)
	}
	a.mu.Lock()
	a.lastSymbols = symbols
	a.mu.Unlock()
	slog.InfoContext(ctx, "aster_subscribed", "symbols", symbols)
	return nil
}

func (a *AsterAdapter) ReadFrame(ctx context.Context) ([]byte, string, error) {
	a.mu.Lock()
	conn := a.conn
	a.mu.Unlock()
	if conn == nil {
		return nil, "", fmt.Errorf("aster: not connected")
	}
	_, data, err := conn.Read(ctx)
	if err != nil {
		a.mu.Lock()
		a.connected = false
		a.mu.Unlock()
		metrics.ErrorEvents.WithLabelValues("aster_read").Inc()
		metrics.ConnectionState.Set(2)
		return nil, "", fmt.Errorf("aster read: %w", err)
	}
	if isAsterPong(data) {
		return a.ReadFrame(ctx)
	}
	metrics.FramesReceived.Inc()
	traceID := a.tracer.Generate()
	return data, traceID, nil
}

func (a *AsterAdapter) Ping(ctx context.Context) error {
	a.mu.Lock()
	conn := a.conn
	a.mu.Unlock()
	if conn == nil {
		return fmt.Errorf("aster: not connected")
	}
	if err := conn.Write(ctx, websocket.MessageText, []byte(`{"op":"ping"}`)); err != nil {
		metrics.HeartbeatFailures.Inc()
		return fmt.Errorf("aster ping: %w", err)
	}
	return nil
}

func (a *AsterAdapter) Close() error {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.conn != nil {
		err := a.conn.Close(websocket.StatusNormalClosure, "")
		a.conn = nil
		a.connected = false
		metrics.ConnectionState.Set(0)
		return err
	}
	return nil
}

func (a *AsterAdapter) IsConnected() bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.connected
}

func isAsterPong(data []byte) bool {
	s := string(data)
	return strings.Contains(s, `"op":"pong"`) || strings.Contains(s, `"op": "pong"`)
}

func quoteArgs(args []string) string {
	quoted := make([]string, len(args))
	for i, a := range args {
		quoted[i] = fmt.Sprintf(`"%s"`, a)
	}
	return strings.Join(quoted, ",")
}
