package main

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"atlas.ai/message-broker/internal/envelope"
	"atlas.ai/message-broker/internal/health"
	"atlas.ai/message-broker/internal/transport"
)

// subscriberBuffer holds messages for a topic until consumed via /subscribe.
type subscriberBuffer struct {
	mu       sync.Mutex
	messages [][]byte
	maxSize  int
}

func newSubscriberBuffer(maxSize int) *subscriberBuffer {
	return &subscriberBuffer{
		messages: make([][]byte, 0),
		maxSize:  maxSize,
	}
}

func (sb *subscriberBuffer) push(data []byte) {
	sb.mu.Lock()
	defer sb.mu.Unlock()
	if len(sb.messages) >= sb.maxSize {
		slog.Warn("subscriber buffer full, dropping oldest message")
		sb.messages = sb.messages[1:]
	}
	cp := make([]byte, len(data))
	copy(cp, data)
	sb.messages = append(sb.messages, cp)
}

func (sb *subscriberBuffer) drain() [][]byte {
	sb.mu.Lock()
	defer sb.mu.Unlock()
	msgs := sb.messages
	sb.messages = make([][]byte, 0)
	return msgs
}

func main() {
	t := transport.NewChannelTransport()
	buffers := make(map[string]*subscriberBuffer)
	var buffersMu sync.RWMutex

	mux := http.NewServeMux()
	mux.HandleFunc("/health", health.Handler())

	mux.HandleFunc("/publish", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		body, err := io.ReadAll(r.Body)
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		msg, err := envelope.Validate(body)
		if err != nil {
			slog.Warn("invalid envelope", "err", err)
			w.WriteHeader(http.StatusBadRequest)
			_, _ = w.Write([]byte(err.Error()))
			return
		}
		topic := msg.MessageType
		if err := t.Publish(topic, body); err != nil {
			slog.Error("publish failed", "err", err)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		slog.Info("message published", "topic", topic, "source", msg.SourceEngine)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"published"}`))
	})

	mux.HandleFunc("/subscribe", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		topic := r.URL.Query().Get("topic")
		if topic == "" {
			w.WriteHeader(http.StatusBadRequest)
			_, _ = w.Write([]byte(`{"error":"topic parameter required"}`))
			return
		}

		// Get or create buffer for this topic
		buffersMu.RLock()
		buf, exists := buffers[topic]
		buffersMu.RUnlock()

		if !exists {
			buffersMu.Lock()
			buf, exists = buffers[topic]
			if !exists {
				buf = newSubscriberBuffer(1024)
				buffers[topic] = buf
				// Subscribe to transport with buffering handler
				err := t.Subscribe(topic, func(data []byte) error {
					buf.push(data)
					return nil
				})
				if err != nil {
					buffersMu.Unlock()
					slog.Error("subscribe failed", "topic", topic, "err", err)
					w.WriteHeader(http.StatusInternalServerError)
					return
				}
				slog.Info("subscriber registered", "topic", topic)
			}
			buffersMu.Unlock()
		}

		msgs := buf.drain()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		if len(msgs) == 0 {
			_, _ = w.Write([]byte(`[]`))
			return
		}
		// Write as JSON array of raw JSON objects (not base64)
		_, _ = w.Write([]byte("["))
		for i, msg := range msgs {
			if i > 0 {
				_, _ = w.Write([]byte(","))
			}
			_, _ = w.Write(msg)
		}
		_, _ = w.Write([]byte("]"))
	})

	srv := &http.Server{Addr: ":8090", Handler: mux}
	go func() {
		slog.Info("message broker listening on :8090")
		if err := srv.ListenAndServe(); err != http.ErrServerClosed {
			slog.Error("server error", "err", err)
		}
	}()
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	slog.Info("shutting down...")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = t.Close()
	_ = srv.Shutdown(ctx)
	slog.Info("broker stopped")
}
