// MODULE: atlas-gateway
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// WARNING: Bounded channels. Non-blocking send. No goroutine leaks.
package feed

import (
	"log/slog"
	"sync"

	"github.com/atlas-ai/services/gateway/internal/metering"
)

type Hub struct {
	mu         sync.RWMutex
	clients    map[string]*Client
	register   chan *Client
	unregister chan *Client
	broadcast  chan []byte
	done       chan struct{}
	meter      *metering.Meter
}

func NewHub() *Hub {
	return &Hub{
		clients:    make(map[string]*Client),
		register:   make(chan *Client, 256),
		unregister: make(chan *Client, 256),
		broadcast:  make(chan []byte, 1024),
		done:       make(chan struct{}),
	}
}

func (h *Hub) AttachMeter(m *metering.Meter) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.meter = m
}

func (h *Hub) Run() {
	for {
		select {
		case c := <-h.register:
			h.mu.Lock()
			h.clients[c.ID] = c
			h.mu.Unlock()
			slog.Info("client_registered", "client_id", c.ID, "total", len(h.clients))
		case c := <-h.unregister:
			h.mu.Lock()
			if _, ok := h.clients[c.ID]; ok {
				delete(h.clients, c.ID)
				close(c.Send)
			}
			h.mu.Unlock()
			slog.Info("client_unregistered", "client_id", c.ID, "total", len(h.clients))
		case msg := <-h.broadcast:
			h.mu.RLock()
			for _, c := range h.clients {
				select {
				case c.Send <- msg:
				default:
					slog.Warn("frame_dropped", "client_id", c.ID, "reason", "buffer_full")
					if h.meter != nil {
						h.meter.RecordFrame(c.Customer.Name, 0, true)
					}
				}
			}
			h.mu.RUnlock()
		case <-h.done:
			return
		}
	}
}

func (h *Hub) Broadcast(frame []byte) {
	select {
	case h.broadcast <- frame:
	default:
		slog.Warn("hub_broadcast_dropped", "reason", "channel_full")
	}
}

func (h *Hub) Stop() {
	close(h.done)
}

func (h *Hub) ClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients)
}
