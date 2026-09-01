// MODULE: atlas-ws-ingestion
// GOVERNANCE: Bybit adapter tests per CR-P0-004 v3 Section F
// F2: Mock server integration (no external network)
// F4: Failure mode tests

package adapter

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"nhooyr.io/websocket"
)

func newMockBybitServer(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "")

		ctx := context.Background()

		// Send subscription confirmation
		conn.Write(ctx, websocket.MessageText, []byte(`{"success":true,"ret_msg":"","conn_id":"test","op":"subscribe"}`))

		// Send ticker frames
		for i := 0; i < 5; i++ {
			frame := `{"topic":"tickers.BTCUSDT","data":{"symbol":"BTCUSDT","lastPrice":"65432.10"},"ts":1725148800000}`
			if err := conn.Write(ctx, websocket.MessageText, []byte(frame)); err != nil {
				return
			}
			time.Sleep(10 * time.Millisecond)
		}

		// Keep alive briefly
		time.Sleep(500 * time.Millisecond)
	}))
	t.Cleanup(srv.Close)
	return srv
}

func TestBybitAdapter_Name(t *testing.T) {
	a := NewBybitAdapter(Config{})
	if a.Name() != "bybit" {
		t.Fatalf("expected 'bybit', got %q", a.Name())
	}
}

func TestBybitAdapter_ConnectAndRead_DataFlow(t *testing.T) {
	srv := newMockBybitServer(t)

	cfg := Config{
		Testnet: true,
		Symbols: []string{"BTCUSDT"},
	}
	a := NewBybitAdapter(cfg)

	// Override URL to mock server
	wsURL := "ws" + srv.URL[4:]

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	// Connect using internal method with custom URL
	a.mu.Lock()
	conn, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		a.mu.Unlock()
		t.Fatalf("dial failed: %v", err)
	}
	a.conn = conn
	a.connected = true
	a.mu.Unlock()

	// Read frames and verify trace_id
	for i := 0; i < 5; i++ {
		frame, traceID, err := a.ReadFrame(ctx)
		if err != nil {
			t.Fatalf("ReadFrame %d failed: %v", i, err)
		}
		if len(frame) == 0 {
			t.Fatalf("ReadFrame %d returned empty frame", i)
		}
		if traceID == "" {
			t.Fatalf("ReadFrame %d returned empty trace_id", i)
		}
		// Verify trace_id format: bybit-{ts}-{seq}
		if traceID[:6] != "bybit-" {
			t.Fatalf("trace_id missing exchange prefix: %q", traceID)
		}
	}

	a.Close()
}

func TestBybitAdapter_ReadFrame_NotConnected(t *testing.T) {
	a := NewBybitAdapter(Config{})
	ctx := context.Background()

	_, _, err := a.ReadFrame(ctx)
	if err == nil {
		t.Fatal("expected error when not connected, got nil")
	}
}

func TestBybitAdapter_Subscribe_NotConnected(t *testing.T) {
	a := NewBybitAdapter(Config{})
	ctx := context.Background()

	err := a.Subscribe(ctx, []string{"BTCUSDT"})
	if err == nil {
		t.Fatal("expected error when not connected, got nil")
	}
}

func TestBybitAdapter_Ping_NotConnected(t *testing.T) {
	a := NewBybitAdapter(Config{})
	ctx := context.Background()

	err := a.Ping(ctx)
	if err == nil {
		t.Fatal("expected error when not connected, got nil")
	}
}

func TestBybitAdapter_Close_Idempotent(t *testing.T) {
	a := NewBybitAdapter(Config{})
	if err := a.Close(); err != nil {
		t.Fatalf("first Close failed: %v", err)
	}
	if err := a.Close(); err != nil {
		t.Fatalf("second Close failed: %v", err)
	}
}

func TestBybitAdapter_IsConnected_DefaultFalse(t *testing.T) {
	a := NewBybitAdapter(Config{})
	if a.IsConnected() {
		t.Fatal("expected IsConnected()=false before Connect()")
	}
}
