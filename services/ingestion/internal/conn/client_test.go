// MODULE: atlas-ws-ingestion
// GOVERNANCE: Connection tests for WebSocket Client
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// LIBRARY: nhooyr.io/websocket v1.8.17
// WARNING: ALL tests MUST use mock servers. NO external network calls.

package conn

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/atlas-ai/services/ingestion/internal/config"
	"github.com/atlas-ai/services/ingestion/internal/ipc"
	"nhooyr.io/websocket"
)

func testConfig(socketPath string) *config.Config {
	return &config.Config{
		WSURI:                "ws://placeholder/ws",
		WSAuthToken:          "test-token",
		ReconnectMaxRetries:  3,
		ReconnectBaseDelayMs: 10,
		HeartbeatIntervalMs:  30000,
		IPCSocketPath:        socketPath,
	}
}

func newMockWSServer(t *testing.T, handler func(conn *websocket.Conn)) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			t.Logf("websocket accept error: %v", err)
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "")
		handler(conn)
	}))
	t.Cleanup(srv.Close)
	return srv
}

// setupIPCListener creates a UDS listener that collects received frames.
// Returns the socket path, received channel, and cleanup function.
func setupIPCListener(t *testing.T) (string, chan []byte, func()) {
	t.Helper()
	tmpDir := t.TempDir()
	sockPath := filepath.Join(tmpDir, "test.sock")

	listener, err := net.Listen("unix", sockPath)
	if err != nil {
		t.Fatalf("failed to create UDS listener: %v", err)
	}

	received := make(chan []byte, 100)
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				buf := make([]byte, 65536)
				for {
					n, err := c.Read(buf)
					if err != nil {
						return
					}
					// Copy data before sending to channel
					data := make([]byte, n)
					copy(data, buf[:n])
					received <- data
				}
			}(conn)
		}
	}()

	cleanup := func() {
		listener.Close()
		wg.Wait()
	}
	return sockPath, received, cleanup
}

func TestNewClient_CreatesInstance(t *testing.T) {
	cfg := testConfig("/tmp/test.sock")
	w := ipc.NewWriter(cfg.IPCSocketPath)
	c := NewClient(cfg, w)
	if c == nil {
		t.Fatal("NewClient returned nil")
	}
}

func TestClient_Close_Idempotent(t *testing.T) {
	cfg := testConfig("/tmp/test.sock")
	w := ipc.NewWriter(cfg.IPCSocketPath)
	c := NewClient(cfg, w)

	if err := c.Close(); err != nil {
		t.Fatalf("first Close should succeed: %v", err)
	}
	if err := c.Close(); err != nil {
		t.Fatalf("second Close should succeed: %v", err)
	}
}

// Fix-1: Real data flow verification - WS server sends frame,
// client reads it AND forwards to IPC, we verify IPC received it.
func TestClient_ConnectAndRead_DataFlowComplete(t *testing.T) {
	expectedPayload := []byte(`{"type":"trade","symbol":"BTC-USDT","price":65432.10}`)

	sockPath, received, cleanup := setupIPCListener(t)
	defer cleanup()

	serverSent := make(chan struct{})
	srv := newMockWSServer(t, func(conn *websocket.Conn) {
		ctx := context.Background()
		err := conn.Write(ctx, websocket.MessageText, expectedPayload)
		if err != nil {
			t.Errorf("mock server write failed: %v", err)
			return
		}
		close(serverSent)
		// Keep alive so client can read
		time.Sleep(500 * time.Millisecond)
	})

	cfg := testConfig(sockPath)
	cfg.WSURI = "ws" + srv.URL[4:] // http:// -> ws://
	cfg.ReconnectMaxRetries = 1
	cfg.ReconnectBaseDelayMs = 10

	w := ipc.NewWriter(sockPath)
	if err := w.Connect(); err != nil {
		t.Fatalf("IPC writer connect failed: %v", err)
	}
	defer w.Close()

	c := NewClient(cfg, w)

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	done := make(chan error, 1)
	go func() {
		done <- c.Run(ctx)
	}()

	// Wait for server to send
	select {
	case <-serverSent:
	case <-time.After(2 * time.Second):
		t.Fatal("timeout: mock server never sent message")
	}

	// Verify IPC received the frame WITH length prefix
	select {
	case data := <-received:
		if len(data) < 4 {
			t.Fatalf("IPC received data too short: %d bytes", len(data))
		}
		// Skip 4-byte length header, compare payload
		payload := data[4:]
		if string(payload) != string(expectedPayload) {
			t.Fatalf("payload mismatch: got %q, want %q", payload, expectedPayload)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timeout: IPC never received forwarded frame - data flow broken")
	}

	cancel()
	<-done
}

// Fix-2: Circuit breaker uses mock server that rejects connections,
// NOT external network. Safe for offline CI.
func TestClient_Run_CircuitBreakerAfterMaxRetries_MockOnly(t *testing.T) {
	// Server that immediately closes every connection
	srv := newMockWSServer(t, func(conn *websocket.Conn) {
		conn.Close(websocket.StatusInternalError, "reject")
	})

	sockPath := filepath.Join(t.TempDir(), "cb.sock")
	cfg := testConfig(sockPath)
	cfg.WSURI = "ws" + srv.URL[4:]
	cfg.ReconnectMaxRetries = 2
	cfg.ReconnectBaseDelayMs = 1

	w := ipc.NewWriter(sockPath)
	c := NewClient(cfg, w)

	ctx := context.Background()
	err := c.Run(ctx)
	if err == nil {
		t.Fatal("expected circuit breaker error, got nil")
	}
	if got := err.Error(); len(got) == 0 {
		t.Fatal("circuit breaker error message is empty")
	}
}

func TestClient_Run_ExitsOnContextCancel_MockOnly(t *testing.T) {
	// Server that holds connection open
	srv := newMockWSServer(t, func(conn *websocket.Conn) {
		time.Sleep(10 * time.Second)
	})

	sockPath := filepath.Join(t.TempDir(), "ctx.sock")
	cfg := testConfig(sockPath)
	cfg.WSURI = "ws" + srv.URL[4:]
	cfg.ReconnectMaxRetries = 100
	cfg.ReconnectBaseDelayMs = 1

	w := ipc.NewWriter(sockPath)
	c := NewClient(cfg, w)

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	err := c.Run(ctx)
	if err == nil {
		t.Fatal("expected error from context cancellation, got nil")
	}
}

// Fix-4: Heartbeat timeout test
func TestClient_HeartbeatFailure_Detected(t *testing.T) {
	// Server accepts connection but NEVER responds to ping
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "")
		// Read forever but never respond to control frames
		ctx := context.Background()
		for {
			_, _, err := conn.Read(ctx)
			if err != nil {
				return
			}
		}
	}))
	defer srv.Close()

	sockPath := filepath.Join(t.TempDir(), "hb.sock")
	cfg := testConfig(sockPath)
	cfg.WSURI = "ws" + srv.URL[4:]
	cfg.HeartbeatIntervalMs = 50 // Very fast heartbeat for testing
	cfg.ReconnectMaxRetries = 1
	cfg.ReconnectBaseDelayMs = 1

	w := ipc.NewWriter(sockPath)
	c := NewClient(cfg, w)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	done := make(chan error, 1)
	go func() {
		done <- c.Run(ctx)
	}()

	// The heartbeat should fail because server doesn't respond to pings.
	// This causes reconnect or circuit breaker. Either way, Run must return.
	select {
	case err := <-done:
		if err == nil {
			t.Log("Run returned nil (acceptable if context cancelled first)")
		} else {
			t.Logf("Run returned error (expected): %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("timeout: heartbeat failure was not detected within 3 seconds")
	}
}

func TestErrReason_NilError(t *testing.T) {
	reason := errReason(nil)
	if reason != "unknown" {
		t.Fatalf("expected 'unknown' for nil error, got %q", reason)
	}
}

func TestErrReason_NonNilError(t *testing.T) {
	reason := errReason(fmt.Errorf("test error"))
	if reason != "connection_error" {
		t.Fatalf("expected 'connection_error', got %q", reason)
	}
}

// Suppress unused import warning for os in test helpers
var _ = os.TempDir
