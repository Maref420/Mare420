package main

import (
	"context"
	"fmt"
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

// transportChecker verifies the transport layer is operational.
type transportChecker struct {
	t transport.Transport
}

func (c *transportChecker) Name() string { return "transport" }

func (c *transportChecker) Check(_ context.Context) error {
	if c.t == nil {
		return fmt.Errorf("transport not initialized")
	}
	// ChannelTransport is always ready once created.
	// Future NATS implementation would check connection here.
	return nil
}

func main() {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	serviceName := "message-broker"
	version := os.Getenv("ATLAS_SERVICE_VERSION")
	if version == "" {
		version = "dev"
	}

	t := transport.NewChannelTransport()
	buffers := make(map[string]*subscriberBuffer)
	var buffersMu sync.RWMutex

	// Health server with transport dependency checker
	checker := &transportChecker{t: t}
	healthServer := health.NewServer(serviceName, version, checker)

	mux := http.NewServeMux()

	// Health routes mounted BEFORE business routes
	healthServer.RegisterRoutes(mux)

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
			slog.WarnContext(ctx, "invalid envelope", "err", err)
			w.WriteHeader(http.StatusBadRequest)
			_, _ = w.Write([]byte(err.Error()))
			return
		}
		topic := msg.MessageType
		if err := t.Publish(topic, body); err != nil {
			slog.ErrorContext(ctx, "publish failed", "err", err)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		slog.InfoContext(ctx, "message published", "topic", topic, "source", msg.SourceEngine)
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
		buffersMu.RLock()
		buf, exists := buffers[topic]
		buffersMu.RUnlock()
		if !exists {
			buffersMu.Lock()
			buf, exists = buffers[topic]
			if !exists {
				buf = newSubscriberBuffer(1024)
				buffers[topic] = buf
				err := t.Subscribe(topic, func(data []byte) error {
					buf.push(data)
					return nil
				})
				if err != nil {
					buffersMu.Unlock()
					slog.ErrorContext(ctx, "subscribe failed", "topic", topic, "err", err)
					w.WriteHeader(http.StatusInternalServerError)
					return
				}
				slog.InfoContext(ctx, "subscriber registered", "topic", topic)
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
		_, _ = w.Write([]byte("["))
		for i, msg := range msgs {
			if i > 0 {
				_, _ = w.Write([]byte(","))
			}
			_, _ = w.Write(msg)
		}
		_, _ = w.Write([]byte("]"))
	})

	srv := &http.Server{
		Addr:         ":8090",
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	go func() {
		slog.InfoContext(ctx, "started", "service", serviceName, "port", 8090)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.ErrorContext(ctx, "server error", "err", err)
			cancel()
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	slog.InfoContext(ctx, "shutdown_signal_received")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := t.Close(); err != nil {
		slog.ErrorContext(ctx, "transport close error", "err", err)
	}
	if err := srv.Shutdown(shutdownCtx); err != nil {
		slog.ErrorContext(ctx, "shutdown_error", "err", err)
	}
	slog.InfoContext(ctx, "stopped")
}
