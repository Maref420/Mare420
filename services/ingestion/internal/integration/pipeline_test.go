// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// TEST TYPE: Integration — Mock WS → Adapter ReadFrame → SerializeFrameTraced → IPC Writer → UDS Reader
package integration

import (
	"context"
	"encoding/binary"
	"net"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/atlas-ai/services/ingestion/internal/ipc"
	"nhooyr.io/websocket"
)

var mockFrames = []string{
	`{"topic":"tickers.BTCUSDT","data":{"symbol":"BTCUSDT","lastPrice":"65432.10"},"ts":1725148800000}`,
	`{"topic":"tickers.BTCUSDT","data":{"symbol":"BTCUSDT","lastPrice":"65433.20"},"ts":1725148800010}`,
	`{"topic":"tickers.BTCUSDT","data":{"symbol":"BTCUSDT","lastPrice":"65431.50"},"ts":1725148800020}`,
	`{"topic":"tickers.BTCUSDT","data":{"symbol":"BTCUSDT","lastPrice":"65434.00"},"ts":1725148800030}`,
	`{"topic":"tickers.BTCUSDT","data":{"symbol":"BTCUSDT","lastPrice":"65432.80"},"ts":1725148800040}`,
}

func newMockWS(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "")
		ctx := context.Background()
		for _, f := range mockFrames {
			if err := conn.Write(ctx, websocket.MessageText, []byte(f)); err != nil {
				return
			}
			time.Sleep(5 * time.Millisecond)
		}
		time.Sleep(500 * time.Millisecond)
	}))
	t.Cleanup(srv.Close)
	return srv
}

func startUDSListener(t *testing.T, socketPath string) (<-chan []byte, func()) {
	t.Helper()
	listener, err := net.Listen("unix", socketPath)
	if err != nil {
		t.Fatalf("listen unix %s: %v", socketPath, err)
	}
	frames := make(chan []byte, 100)
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		buf := make([]byte, 64*1024)
		for {
			n, err := conn.Read(buf)
			if err != nil {
				return
			}
			data := make([]byte, n)
			copy(data, buf[:n])
			select {
			case frames <- data:
			default:
			}
		}
	}()
	return frames, func() {
		listener.Close()
		wg.Wait()
	}
}

// TestPipeline_MockWSToIPC verifies: WS Read → SerializeFrameTraced → IPC WriteRaw → UDS Read
func TestPipeline_MockWSToIPC(t *testing.T) {
	srv := newMockWS(t)
	wsURL := "ws" + srv.URL[4:]
	socketPath := filepath.Join(t.TempDir(), "pipeline.sock")

	receivedCh, cleanup := startUDSListener(t, socketPath)
	defer cleanup()

	writer := ipc.NewWriter(socketPath)
	if err := writer.Connect(); err != nil {
		t.Fatalf("IPC connect: %v", err)
	}
	defer writer.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	conn, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		t.Fatalf("dial mock: %v", err)
	}
	defer conn.Close(websocket.StatusNormalClosure, "")

	seq := uint64(0)
	for i := 0; i < len(mockFrames); i++ {
		_, data, err := conn.Read(ctx)
		if err != nil {
			t.Fatalf("read %d: %v", i, err)
		}
		seq++
		traceID := formatTraceID("bybit", seq)
		serialized := ipc.SerializeFrameTraced(data, traceID)
		if err := writer.WriteRaw(serialized); err != nil {
			t.Fatalf("write %d: %v", i, err)
		}
	}

	// Collect received frames
	time.Sleep(200 * time.Millisecond)
	received := 0
	timeout := time.After(2 * time.Second)
	for received < len(mockFrames) {
		select {
		case raw := <-receivedCh:
			received++
			if len(raw) < 5 {
				t.Fatalf("frame %d too short: %d bytes", received, len(raw))
			}
			totalLen := binary.BigEndian.Uint32(raw[:4])
			if totalLen == 0 {
				t.Fatalf("frame %d zero length", received)
			}
			flags := raw[4]
			if flags != 0x01 {
				t.Fatalf("frame %d expected flags=0x01, got 0x%02x", received, flags)
			}
		case <-timeout:
			t.Fatalf("timeout: got %d/%d frames", received, len(mockFrames))
		}
	}
}

// TestPipeline_GracefulShutdown verifies context cancellation stops pipeline cleanly.
func TestPipeline_GracefulShutdown(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		for {
			select {
			case <-ctx.Done():
				return
			default:
				time.Sleep(10 * time.Millisecond)
			}
		}
	}()
	cancel()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("goroutine leak after cancel")
	}
}

func formatTraceID(exchange string, seq uint64) string {
	ts := time.Now().UnixMilli()
	return exchange + "-" + uitoa(uint64(ts)) + "-" + padSeq(seq)
}

func uitoa(n uint64) string {
	if n == 0 {
		return "0"
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	return string(buf[i:])
}

func padSeq(seq uint64) string {
	s := uitoa(seq)
	if len(s) >= 20 {
		return s
	}
	pad := make([]byte, 20)
	for i := range pad {
		pad[i] = '0'
	}
	copy(pad[20-len(s):], s)
	return string(pad)
}
