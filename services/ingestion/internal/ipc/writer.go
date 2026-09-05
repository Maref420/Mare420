// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml
// WARNING: NEVER silently drop frames. Backpressure must be explicit and observable.

package ipc

import (
	"fmt"
	"net"
	"sync"
	"time"

	"github.com/atlas-ai/services/ingestion/internal/metrics"
)

const (
	maxBufferSize    = 1000
	writeTimeout     = 5 * time.Second
	maxFrameSize     = 16 * 1024 * 1024 // 16 MB per spec
)

type Writer struct {
	socketPath string
	conn       net.Conn
	buffer     chan []byte
	done       chan struct{}
	mu         sync.Mutex
	closed     bool
}

func NewWriter(socketPath string) *Writer {
	return &Writer{
		socketPath: socketPath,
		buffer:     make(chan []byte, maxBufferSize),
		done:       make(chan struct{}),
	}
}

func (w *Writer) Connect() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.closed {
		return fmt.Errorf("writer is closed")
	}

	conn, err := net.Dial("unix", w.socketPath)
	if err != nil {
		return fmt.Errorf("failed to connect to IPC socket %s: %w", w.socketPath, err)
	}

	w.conn = conn
	go w.writeLoop()
	return nil
}

func (w *Writer) Write(payload []byte) error {
	if len(payload) == 0 {
		return fmt.Errorf("zero-length payload rejected per ipc-binary-v1 spec")
	}
	if len(payload) > maxFrameSize {
		return fmt.Errorf("payload size %d exceeds max %d per ipc-binary-v1 spec", len(payload), maxFrameSize)
	}

	frame := SerializeFrame(payload)

	select {
	case w.buffer <- frame:
		metrics.IPCBackpressure.Set(float64(len(w.buffer)))
		return nil
	default:
		// Buffer full: drop oldest frame to make room
		select {
		case <-w.buffer:
			metrics.FramesDropped.WithLabelValues("backpressure").Inc()
		default:
		}

		select {
		case w.buffer <- frame:
			metrics.IPCBackpressure.Set(float64(len(w.buffer)))
			return nil
		default:
			metrics.FramesDropped.WithLabelValues("backpressure_overflow").Inc()
			return fmt.Errorf("IPC buffer overflow: frame dropped after backpressure eviction")
		}
	}
}

func (w *Writer) writeLoop() {
	for {
		select {
		case frame := <-w.buffer:
			metrics.IPCBackpressure.Set(float64(len(w.buffer)))
			if w.conn == nil {
				metrics.FramesDropped.WithLabelValues("no_connection").Inc()
				continue
			}
			w.conn.SetWriteDeadline(time.Now().Add(writeTimeout))
			n, err := w.conn.Write(frame)
			if err != nil {
				metrics.ErrorEvents.WithLabelValues("ipc_write").Inc()
				continue
			}
			if n != len(frame) {
				metrics.ErrorEvents.WithLabelValues("ipc_partial_write").Inc()
				continue
			}
			metrics.FramesForwarded.Inc()
		case <-w.done:
			return
		}
	}
}

func (w *Writer) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.closed {
		return nil
	}

	w.closed = true
	close(w.done)

	if w.conn != nil {
		return w.conn.Close()
	}
	return nil
}

// WriteRaw sends a pre-serialized frame (already includes length header + flags + trace)
// WITHOUT re-wrapping via SerializeFrame(). Use this when the caller has already
// constructed the complete binary frame via SerializeFrameTraced() or SerializeFrame().
// GOVERNANCE: No parallel path — same buffer/channel as Write(), just skips re-serialization.
func (w *Writer) WriteRaw(frame []byte) error {
	if len(frame) == 0 {
		return fmt.Errorf("zero-length raw frame rejected per ipc-binary-v1 spec")
	}
	if len(frame) > maxFrameSize+4 {
		return fmt.Errorf("raw frame size %d exceeds max %d per ipc-binary-v1 spec", len(frame), maxFrameSize+4)
	}
	select {
	case w.buffer <- frame:
		metrics.IPCBackpressure.Set(float64(len(w.buffer)))
		return nil
	default:
		select {
		case <-w.buffer:
			metrics.FramesDropped.WithLabelValues("backpressure").Inc()
		default:
		}
		select {
		case w.buffer <- frame:
			metrics.IPCBackpressure.Set(float64(len(w.buffer)))
			return nil
		default:
			metrics.FramesDropped.WithLabelValues("backpressure_overflow").Inc()
			return fmt.Errorf("IPC buffer overflow: raw frame dropped after backpressure eviction")
		}
	}
}
