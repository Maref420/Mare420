// MODULE: atlas-gateway
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// CONTRACT: Reads IPC frames from Unix socket, broadcasts to Hub.
// SPEC: ipc-binary-v1.spec.yaml — 4-byte BE length + 1-byte flags + payload
package feed

import (
	"context"
	"encoding/binary"
	"io"
	"log/slog"
	"net"
	"sync"

	"github.com/atlas-ai/services/gateway/internal/metering"
	"github.com/prometheus/client_golang/prometheus"
)

type Bridge struct {
	hub        *Hub
	meter      *metering.Meter
	socketPath string
	done       chan struct{}
	listener   net.Listener
	wg         sync.WaitGroup
	framesVec  *prometheus.CounterVec
	bytesVec   *prometheus.CounterVec
	droppedVec *prometheus.CounterVec
}

func NewBridge(hub *Hub, meter *metering.Meter, socketPath string, framesVec, bytesVec, droppedVec *prometheus.CounterVec) *Bridge {
	return &Bridge{
		hub:        hub,
		meter:      meter,
		socketPath: socketPath,
		done:       make(chan struct{}),
		framesVec:  framesVec,
		bytesVec:   bytesVec,
		droppedVec: droppedVec,
	}
}

func (b *Bridge) Start(ctx context.Context) error {
	lis, err := net.Listen("unix", b.socketPath)
	if err != nil {
		return err
	}
	b.listener = lis
	slog.Info("bridge_listening", "socket", b.socketPath)
	b.wg.Add(1)
	go b.acceptLoop(ctx)
	return nil
}

func (b *Bridge) acceptLoop(ctx context.Context) {
	defer b.wg.Done()
	for {
		select {
		case <-b.done:
			return
		case <-ctx.Done():
			return
		default:
		}
		conn, err := b.listener.Accept()
		if err != nil {
			select {
			case <-b.done:
				return
			case <-ctx.Done():
				return
			default:
				slog.Error("bridge_accept_error", "error", err)
				continue
			}
		}
		b.wg.Add(1)
		go b.handleConnection(conn, ctx)
	}
}

func (b *Bridge) handleConnection(conn net.Conn, ctx context.Context) {
	defer b.wg.Done()
	defer conn.Close()
	header := make([]byte, 5)
	for {
		select {
		case <-b.done:
			return
		case <-ctx.Done():
			return
		default:
		}
		if _, err := io.ReadFull(conn, header); err != nil {
			if err != io.EOF {
				slog.Debug("bridge_read_header_error", "error", err)
			}
			return
		}
		frameLen := binary.BigEndian.Uint32(header[0:4])
		flags := header[4]
		_ = flags // traced flag for future use

		if frameLen == 0 || frameLen > 10*1024*1024 {
			slog.Warn("bridge_invalid_frame_length", "length", frameLen)
			return
		}
		payload := make([]byte, frameLen)
		if _, err := io.ReadFull(conn, payload); err != nil {
			slog.Debug("bridge_read_payload_error", "error", err)
			return
		}
		labels := prometheus.Labels{"customer": "broadcast"}
		b.framesVec.With(labels).Inc()
		b.bytesVec.With(labels).Add(float64(len(payload)))
		b.meter.RecordFrame("broadcast", len(payload), false)

		select {
		case b.hub.broadcast <- payload:
		default:
			b.droppedVec.With(labels).Inc()
			b.meter.RecordFrame("broadcast", 0, true)
			slog.Warn("bridge_broadcast_dropped")
		}
	}
}

func (b *Bridge) Stop() {
	close(b.done)
	if b.listener != nil {
		b.listener.Close()
	}
	b.wg.Wait()
	slog.Info("bridge_stopped")
}
