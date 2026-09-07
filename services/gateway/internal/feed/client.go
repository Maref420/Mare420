// MODULE: atlas-gateway
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// WARNING: context.Context on every I/O. Graceful close mandatory.
package feed

import (
	"context"
	"crypto/rand"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"github.com/atlas-ai/services/gateway/internal/config"
	"github.com/coder/websocket"
)

type Client struct {
	ID       string
	Customer config.CustomerConfig
	Send     chan []byte
	hub      *Hub
	mu       sync.Mutex
	closed   bool
}

func NewClient(customer config.CustomerConfig, hub *Hub) *Client {
	var b [8]byte
	if _, err := rand.Read(b[:]); err != nil {
		b = [8]byte{0, 0, 0, 0, 0, 0, 0, 1}
	}
	return &Client{
		ID:       fmt.Sprintf("%x", b),
		Customer: customer,
		hub:      hub,
		Send:     make(chan []byte, 256),
	}
}

func (c *Client) ServeWS(w http.ResponseWriter, r *http.Request) error {
	ctx := r.Context()
	conn, err := websocket.Accept(w, r, &websocket.AcceptOptions{
		InsecureSkipVerify: true,
	})
	if err != nil {
		return fmt.Errorf("ws accept: %w", err)
	}
	defer conn.Close(websocket.StatusNormalClosure, "")

	c.hub.register <- c
	defer func() { c.hub.unregister <- c }()

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	wg := sync.WaitGroup{}

	// Read pump
	wg.Add(1)
	go func() {
		defer wg.Done()
		for {
			_, _, err := conn.Read(ctx)
			if err != nil {
				if websocket.CloseStatus(err) != websocket.StatusNormalClosure {
					slog.Debug("read_pump_exit", "client_id", c.ID, "error", err)
				}
				cancel()
				return
			}
		}
	}()

	// Write pump with rate limiting
	wg.Add(1)
	go func() {
		defer wg.Done()
		fps := c.Customer.MaxFPS
		if fps <= 0 {
			fps = 10
		}
		interval := time.Second / time.Duration(fps)
		ticker := time.NewTicker(interval)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case msg, ok := <-c.Send:
				if !ok {
					return
				}
				<-ticker.C // Rate limit
				c.mu.Lock()
				if c.closed {
					c.mu.Unlock()
					return
				}
				writeCtx, writeCancel := context.WithTimeout(ctx, 5*time.Second)
				err := conn.Write(writeCtx, websocket.MessageBinary, msg)
				writeCancel()
				c.mu.Unlock()
				if err != nil {
					slog.Warn("write_error", "client_id", c.ID, "error", err)
					cancel()
					return
				}
			}
		}
	}()

	<-ctx.Done()
	c.mu.Lock()
	c.closed = true
	c.mu.Unlock()
	wg.Wait()
	return nil
}
