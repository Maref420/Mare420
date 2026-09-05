// MODULE: atlas-ws-ingestion
// GOVERNANCE: OKX adapter tests per CR-P0-004 v3 Sections F, D1, D4

package adapter

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"nhooyr.io/websocket"
)

func newMockOKXServer(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "")

		ctx := context.Background()

		// Send subscription confirmation
		conn.Write(ctx, websocket.MessageText, []byte(`{"event":"subscribe","arg":{"channel":"tickers","instId":"BTC-USDT"},"connId":"test"}`))

		// Send ticker frames
		for i := 0; i < 5; i++ {
			frame := `{"arg":{"channel":"tickers","instId":"BTC-USDT"},"data":[{"instId":"BTC-USDT","last":"65432.1","ts":"1725148800000"}]}`
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

func TestOKXAdapter_Name(t *testing.T) {
	a := NewOKXAdapter(Config{})
	if a.Name() != "okx" {
		t.Fatalf("expected 'okx', got %q", a.Name())
	}
}

func TestOKXAdapter_ConnectAndRead_DataFlow(t *testing.T) {
	srv := newMockOKXServer(t)
	cfg := Config{Testnet: true, Symbols: []string{"BTC-USDT"}}
	a := NewOKXAdapter(cfg)

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
		if traceID[:4] != "okx-" {
			t.Fatalf("trace_id missing exchange prefix: %q", traceID)
		}
	}
	a.Close()
}

// Verify pong filtering: server sends pong then real frame
func TestOKXAdapter_ReadFrame_PongFiltered(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "")
		ctx := context.Background()

		// Send pong first (should be filtered)
		conn.Write(ctx, websocket.MessageText, []byte("pong"))
		// Then send real frame
		conn.Write(ctx, websocket.MessageText, []byte(`{"data":"real"}`))
		time.Sleep(200 * time.Millisecond)
	}))
	defer srv.Close()

	a := NewOKXAdapter(Config{Testnet: true})
	wsURL := "ws" + srv.URL[4:]
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
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

	frame, traceID, err := a.ReadFrame(ctx)
	if err != nil {
		t.Fatalf("ReadFrame failed: %v", err)
	}
	if string(frame) != `{"data":"real"}` {
		t.Fatalf("expected real frame, got: %q", string(frame))
	}
	if traceID[:4] != "okx-" {
		t.Fatalf("trace_id prefix wrong: %q", traceID)
	}
	a.Close()
}

func TestOKXAdapter_SubscriptionState_CachedForReconnect(t *testing.T) {
	srv := newMockOKXServer(t)
	a := NewOKXAdapter(Config{Testnet: true})

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

	symbols := []string{"BTC-USDT", "ETH-USDT"}
	if err := a.Subscribe(ctx, symbols); err != nil {
		t.Fatalf("Subscribe failed: %v", err)
	}

	a.mu.Lock()
	if len(a.lastSymbols) != 2 {
		a.mu.Unlock()
		t.Fatalf("expected 2 cached symbols, got %d", len(a.lastSymbols))
	}
	if a.lastSymbols[0] != "BTC-USDT" || a.lastSymbols[1] != "ETH-USDT" {
		a.mu.Unlock()
		t.Fatalf("cached symbols mismatch: %v", a.lastSymbols)
	}
	a.mu.Unlock()
	a.Close()
}

func TestOKXAdapter_RateLimiter_Integrated(t *testing.T) {
	a := NewOKXAdapter(Config{Testnet: true})
	if a.limiter == nil {
		t.Fatal("rate limiter not initialized")
	}
	allowed := 0
	for i := 0; i < 15; i++ {
		if a.limiter.Allow() {
			allowed++
		}
	}
	if allowed != int(okxSubscribeBurst) {
		t.Fatalf("expected %d burst allows, got %d", int(okxSubscribeBurst), allowed)
	}
}

func TestOKXAdapter_ReadFrame_NotConnected(t *testing.T) {
	a := NewOKXAdapter(Config{})
	_, _, err := a.ReadFrame(context.Background())
	if err == nil {
		t.Fatal("expected error when not connected")
	}
}

func TestOKXAdapter_Subscribe_NotConnected(t *testing.T) {
	a := NewOKXAdapter(Config{})
	err := a.Subscribe(context.Background(), []string{"BTC-USDT"})
	if err == nil {
		t.Fatal("expected error when not connected")
	}
}

func TestOKXAdapter_Ping_NotConnected(t *testing.T) {
	a := NewOKXAdapter(Config{})
	err := a.Ping(context.Background())
	if err == nil {
		t.Fatal("expected error when not connected")
	}
}

func TestOKXAdapter_Close_Idempotent(t *testing.T) {
	a := NewOKXAdapter(Config{})
	if err := a.Close(); err != nil {
		t.Fatalf("first Close failed: %v", err)
	}
	if err := a.Close(); err != nil {
		t.Fatalf("second Close failed: %v", err)
	}
}

func TestOKXAdapter_IsConnected_DefaultFalse(t *testing.T) {
	a := NewOKXAdapter(Config{})
	if a.IsConnected() {
		t.Fatal("expected false before Connect()")
	}
}

func TestIsPong(t *testing.T) {
	tests := []struct {
		data   []byte
		expect bool
	}{
		{[]byte("pong"), true},
		{[]byte("ponG"), false},
		{[]byte("pong "), false},
		{[]byte(""), false},
		{[]byte(`{"op":"pong"}`), false},
		{nil, false},
	}
	for _, tt := range tests {
		got := isPong(tt.data)
		if got != tt.expect {
			t.Errorf("isPong(%q) = %v, want %v", tt.data, got, tt.expect)
		}
	}
}
