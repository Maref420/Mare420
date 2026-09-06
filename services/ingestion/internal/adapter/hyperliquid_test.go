// MODULE: atlas-ws-ingestion
// GOVERNANCE: Hyperliquid adapter tests per CR-P0-004 v3 Sections D1, D4, F
package adapter

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"nhooyr.io/websocket"
)

func newMockHyperliquidServer(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "")
		ctx := context.Background()
		// Send subscribe ack
		conn.Write(ctx, websocket.MessageText, []byte(`{"channel":"subscriptionResponse","data":{"method":"subscribe"}}`))
		// Send 5 L2 book frames
		for i := 0; i < 5; i++ {
			frame := `{"channel":"l2Book","data":{"coin":"BTC","levels":[["65432.10","1.5"]]}}`
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

func TestHyperliquidAdapter_Name(t *testing.T) {
	a := NewHyperliquidAdapter(Config{})
	if a.Name() != "hyperliquid" {
		t.Fatalf("expected 'hyperliquid', got %q", a.Name())
	}
}

func TestHyperliquidAdapter_ConnectAndRead_DataFlow(t *testing.T) {
	srv := newMockHyperliquidServer(t)
	cfg := Config{Testnet: true, Symbols: []string{"BTC"}}
	a := NewHyperliquidAdapter(cfg)

	wsURL := "ws" + srv.URL[4:]
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

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
		if len(traceID) < 13 || traceID[:12] != "hyperliquid-" {
			t.Fatalf("trace_id missing exchange prefix: %q", traceID)
		}
	}
}

func TestHyperliquidAdapter_IsConnected_Transitions(t *testing.T) {
	a := NewHyperliquidAdapter(Config{})
	if a.IsConnected() {
		t.Fatal("expected not connected initially")
	}
	a.mu.Lock()
	a.connected = true
	a.mu.Unlock()
	if !a.IsConnected() {
		t.Fatal("expected connected after setting")
	}
	a.mu.Lock()
	a.connected = false
	a.mu.Unlock()
	if a.IsConnected() {
		t.Fatal("expected not connected after reset")
	}
}
