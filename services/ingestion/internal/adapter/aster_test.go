// MODULE: atlas-ws-ingestion
// GOVERNANCE: Aster DEX adapter tests per CR-P0-004 v3 Sections D1, D4, F
package adapter

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"nhooyr.io/websocket"
)

func newMockAsterServer(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "")
		ctx := context.Background()
		// Send subscribe ack
		conn.Write(ctx, websocket.MessageText, []byte(`{"op":"subscribe","success":true}`))
		// Send 5 market data frames
		for i := 0; i < 5; i++ {
			frame := `{"symbol":"BTCUSDT","price":"65432.10","ts":1725148800000}`
			if err := conn.Write(ctx, websocket.MessageText, []byte(frame)); err != nil {
				return
			}
			time.Sleep(10 * time.Millisecond)
		}
		time.Sleep(500 * time.Millisecond)
	}))
	t.Cleanup(srv.Close)
	return srv
}

func TestAsterAdapter_Name(t *testing.T) {
	a := NewAsterAdapter(Config{})
	if a.Name() != "aster" {
		t.Fatalf("expected 'aster', got %q", a.Name())
	}
}

func TestAsterAdapter_ConnectAndRead_DataFlow(t *testing.T) {
	srv := newMockAsterServer(t)
	cfg := Config{Testnet: true, Symbols: []string{"BTCUSDT"}}
	a := NewAsterAdapter(cfg)

	wsURL := "ws" + srv.URL[4:]
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	// Manually set connection to mock server
	a.mu.Lock()
	conn, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		a.mu.Unlock()
		t.Fatalf("dial failed: %v", err)
	}
	a.conn = conn
	a.connected = true
	a.mu.Unlock()

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
		if traceID[:6] != "aster-" {
			t.Fatalf("trace_id missing exchange prefix: %q", traceID)
		}
	}
}

func TestAsterAdapter_IsConnected_Transitions(t *testing.T) {
	a := NewAsterAdapter(Config{})
	if a.IsConnected() {
		t.Fatal("expected not connected initially")
	}
	// Simulate connection
	a.mu.Lock()
	a.connected = true
	a.mu.Unlock()
	if !a.IsConnected() {
		t.Fatal("expected connected after setting")
	}
	// Close resets state
	a.mu.Lock()
	a.connected = false
	a.mu.Unlock()
	if a.IsConnected() {
		t.Fatal("expected not connected after reset")
	}
}
