// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml
// LIBRARY: nhooyr.io/websocket v1.8.17
// WARNING: This module MUST NOT parse, validate, or transform market data.
//          Raw frames are forwarded AS-IS to core_engine/market_data (Rust).

package conn

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"github.com/atlas-ai/services/ingestion/internal/config"
	"github.com/atlas-ai/services/ingestion/internal/ipc"
	"github.com/atlas-ai/services/ingestion/internal/metrics"
	"nhooyr.io/websocket"
)

type Client struct {
	cfg    *config.Config
	writer *ipc.Writer
	done   chan struct{}
	mu     sync.Mutex
	closed bool
}

func NewClient(cfg *config.Config, writer *ipc.Writer) *Client {
	return &Client{
		cfg:    cfg,
		writer: writer,
		done:   make(chan struct{}),
	}
}

func (c *Client) Run(ctx context.Context) error {
	slog.Info("ws-ingestion client starting", "uri", c.cfg.WSURI)
	metrics.ConnectionState.Set(2) // reconnecting

	retryCount := 0
	for {
		select {
		case <-ctx.Done():
			slog.Info("ws-ingestion client stopping: context cancelled")
			metrics.ConnectionState.Set(0) // disconnected
			return ctx.Err()
		case <-c.done:
			slog.Info("ws-ingestion client stopping: closed")
			metrics.ConnectionState.Set(0) // disconnected
			return nil
		default:
		}

		err := c.connectAndRead(ctx)
		if err != nil {
			metrics.ErrorEvents.WithLabelValues(errReason(err)).Inc()
			slog.Error("ws connection failed", "error", err, "attempt", retryCount+1)
		}

		retryCount++
		if retryCount > c.cfg.ReconnectMaxRetries {
			metrics.ConnectionState.Set(3) // circuit_broken
			metrics.ErrorEvents.WithLabelValues("circuit_breaker").Inc()
			return fmt.Errorf("max reconnection attempts (%d) exceeded: circuit breaker open", c.cfg.ReconnectMaxRetries)
		}

		metrics.ReconnectionAttempts.WithLabelValues(errReason(err)).Inc()
		metrics.ConnectionState.Set(2) // reconnecting

		delay := c.cfg.ReconnectBaseDelay() * time.Duration(1<<min(retryCount-1, 6))
		slog.Info("reconnecting", "delay", delay, "attempt", retryCount)

		select {
		case <-time.After(delay):
		case <-ctx.Done():
			metrics.ConnectionState.Set(0)
			return ctx.Err()
		case <-c.done:
			metrics.ConnectionState.Set(0)
			return nil
		}
	}
}

func (c *Client) connectAndRead(ctx context.Context) error {
	header := http.Header{}
	if c.cfg.WSAuthToken != "" {
		header.Set("Authorization", "Bearer "+c.cfg.WSAuthToken)
	}

	wsConn, _, err := websocket.Dial(ctx, c.cfg.WSURI, &websocket.DialOptions{
		HTTPHeader: header,
	})
	if err != nil {
		return fmt.Errorf("websocket dial failed: %w", err)
	}
	defer wsConn.Close(websocket.StatusNormalClosure, "closing")

	metrics.ConnectionState.Set(1) // connected
	slog.Info("websocket connected", "uri", c.cfg.WSURI)

	// Set read limit per IPC spec max frame size (16 MB)
	wsConn.SetReadLimit(16 * 1024 * 1024)

	// Heartbeat goroutine
	hbCtx, hbCancel := context.WithCancel(ctx)
	defer hbCancel()
	go c.heartbeatLoop(hbCtx, wsConn)

	// Read loop
	for {
		select {
		case <-c.done:
			return nil
		default:
		}

		msgType, data, err := wsConn.Read(ctx)
		if err != nil {
			return fmt.Errorf("websocket read failed: %w", err)
		}

		if msgType != websocket.MessageText && msgType != websocket.MessageBinary {
			slog.Warn("unexpected message type", "type", msgType)
			continue
		}

		metrics.FramesReceived.Inc()

		if writeErr := c.writer.Write(data); writeErr != nil {
			slog.Error("IPC write failed", "error", writeErr)
			metrics.ErrorEvents.WithLabelValues("ipc_write_from_ws").Inc()
			// Continue reading; don't break WS connection for IPC issues
		}
	}
}

func (c *Client) heartbeatLoop(ctx context.Context, conn *websocket.Conn) {
	ticker := time.NewTicker(c.cfg.HeartbeatInterval())
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
			err := conn.Ping(pingCtx)
			cancel()
			if err != nil {
				metrics.HeartbeatFailures.Inc()
				slog.Error("heartbeat ping failed", "error", err)
				return
			}
		}
	}
}

func (c *Client) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed {
		return nil
	}

	c.closed = true
	close(c.done)
	return nil
}

func errReason(err error) string {
	if err == nil {
		return "unknown"
	}
	return "connection_error"
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
