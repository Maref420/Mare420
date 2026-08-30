package transport

import (
	"fmt"
	"sync"
)

var ErrTransportClosed = fmt.Errorf("transport closed")

// ErrBufferFull indicates the subscriber channel is at capacity.
// Caller should retry or handle backpressure explicitly.
var ErrBufferFull = fmt.Errorf("subscriber buffer full, message not delivered")

// DefaultBufferSize is the per-subscriber channel capacity.
// Sized for burst absorption without unbounded memory growth.
const DefaultBufferSize = 1024

// ChannelTransport implements Transport using Go channels.
// Stdlib only. No external dependencies.
type ChannelTransport struct {
	mu     sync.RWMutex
	subs   map[string][]chan []byte
	closed bool
}

func NewChannelTransport() *ChannelTransport {
	return &ChannelTransport{subs: make(map[string][]chan []byte)}
}

func (c *ChannelTransport) Publish(topic string, data []byte) error {
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.closed {
		return ErrTransportClosed
	}
	for _, ch := range c.subs[topic] {
		select {
		case ch <- data:
			// delivered
		default:
			// Buffer full — this is a real error, not silent drop
			return ErrBufferFull
		}
	}
	return nil
}

func (c *ChannelTransport) Subscribe(topic string, handler func([]byte) error) error {
	c.mu.Lock()
	ch := make(chan []byte, DefaultBufferSize)
	c.subs[topic] = append(c.subs[topic], ch)
	c.mu.Unlock()
	go func() {
		for msg := range ch {
			_ = handler(msg)
		}
	}()
	return nil
}

func (c *ChannelTransport) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.closed {
		return nil
	}
	c.closed = true
	for _, chs := range c.subs {
		for _, ch := range chs {
			close(ch)
		}
	}
	return nil
}
