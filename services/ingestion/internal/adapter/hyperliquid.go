// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// ADR: docs/decisions/007a-trace-id-propagation-addendum.md
// EXCHANGE: Hyperliquid Public WebSocket
// CHECKLIST: CR-P0-004 v3 Sections A-H
// RATE LIMITS: 5 ops/sec subscribe (D1)
// RECONNECT: State recovery with automatic re-subscribe (D4)
// WARNING: Raw frames only. No parsing, no normalization.
package adapter

import (
	"context"
	"fmt"
	"log/slog"
	"sync"

	"github.com/atlas-ai/services/ingestion/internal/metrics"
	"nhooyr.io/websocket"
)

const (
	hyperTestnetWS      = "wss://api.hyperliquid-testnet.xyz/ws"
	hyperMainnetWS      = "wss://api.hyperliquid.xyz/ws"
	hyperSubscribeRate  = 5.0
	hyperSubscribeBurst = 3.0
)

type HyperliquidAdapter struct {
	cfg         Config
	conn        *websocket.Conn
	mu          sync.Mutex
	connected   bool
	tracer      *TraceGenerator
	limiter     *RateLimiter
	lastSymbols []string
}

func NewHyperliquidAdapter(cfg Config) *HyperliquidAdapter {
	return &HyperliquidAdapter{
		cfg:     cfg,
		tracer:  NewTraceGenerator("hyperliquid"),
		limiter: NewRateLimiter(hyperSubscribeBurst, hyperSubscribeRate),
	}
}

func (h *HyperliquidAdapter) Name() string { return "hyperliquid" }

func (h *HyperliquidAdapter) Connect(ctx context.Context) error {
	h.mu.Lock()
	defer h.mu.Unlock()
	wsURL := hyperMainnetWS
	if h.cfg.Testnet {
		wsURL = hyperTestnetWS
	}
	slog.InfoContext(ctx, "hyperliquid_connecting", "url", wsURL)
	conn, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		metrics.ErrorEvents.WithLabelValues("hyperliquid_connect").Inc()
		return fmt.Errorf("hyperliquid dial: %w", err)
	}
	h.conn = conn
	h.connected = true
	metrics.ConnectionState.Set(1)
	slog.InfoContext(ctx, "hyperliquid_connected")
	return nil
}

func (h *HyperliquidAdapter) Subscribe(ctx context.Context, symbols []string) error {
	h.mu.Lock()
	conn := h.conn
	h.mu.Unlock()
	if conn == nil {
		metrics.ErrorEvents.WithLabelValues("hyperliquid_subscribe_not_connected").Inc()
		return fmt.Errorf("hyperliquid: not connected")
	}
	if err := h.limiter.Wait(ctx); err != nil {
		metrics.ErrorEvents.WithLabelValues("hyperliquid_rate_limited").Inc()
		return fmt.Errorf("hyperliquid rate limit: %w", err)
	}
	for _, symbol := range symbols {
		msg := fmt.Sprintf(`{"method":"subscribe","subscription":{"type":"l2Book","coin":"%s"}}`, symbol)
		if err := conn.Write(ctx, websocket.MessageText, []byte(msg)); err != nil {
			metrics.ErrorEvents.WithLabelValues("hyperliquid_subscribe").Inc()
			return fmt.Errorf("hyperliquid subscribe write: %w", err)
		}
	}
	h.mu.Lock()
	h.lastSymbols = symbols
	h.mu.Unlock()
	slog.InfoContext(ctx, "hyperliquid_subscribed", "symbols", symbols)
	return nil
}

func (h *HyperliquidAdapter) ReadFrame(ctx context.Context) ([]byte, string, error) {
	h.mu.Lock()
	conn := h.conn
	h.mu.Unlock()
	if conn == nil {
		return nil, "", fmt.Errorf("hyperliquid: not connected")
	}
	_, data, err := conn.Read(ctx)
	if err != nil {
		h.mu.Lock()
		h.connected = false
		h.mu.Unlock()
		metrics.ErrorEvents.WithLabelValues("hyperliquid_read").Inc()
		metrics.ConnectionState.Set(2)
		return nil, "", fmt.Errorf("hyperliquid read: %w", err)
	}
	metrics.FramesReceived.Inc()
	traceID := h.tracer.Generate()
	return data, traceID, nil
}

func (h *HyperliquidAdapter) Ping(ctx context.Context) error {
	h.mu.Lock()
	conn := h.conn
	h.mu.Unlock()
	if conn == nil {
		return fmt.Errorf("hyperliquid: not connected")
	}
	if err := conn.Write(ctx, websocket.MessageText, []byte(`{"method":"ping"}`)); err != nil {
		metrics.HeartbeatFailures.Inc()
		return fmt.Errorf("hyperliquid ping: %w", err)
	}
	return nil
}

func (h *HyperliquidAdapter) Close() error {
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.conn != nil {
		err := h.conn.Close(websocket.StatusNormalClosure, "")
		h.conn = nil
		h.connected = false
		metrics.ConnectionState.Set(0)
		return err
	}
	return nil
}

func (h *HyperliquidAdapter) IsConnected() bool {
	h.mu.Lock()
	defer h.mu.Unlock()
	return h.connected
}
