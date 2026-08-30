package main

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"atlas.ai/message-broker/internal/envelope"
	"atlas.ai/message-broker/internal/health"
	"atlas.ai/message-broker/internal/transport"
)

func main() {
	t := transport.NewChannelTransport()
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
