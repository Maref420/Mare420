// MODULE: atlas-ws-ingestion
// GOVERNANCE: Bybit adapter tests per CR-P0-004 v3 Sections D1, D4, F

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
		conn.Write(ctx, websocket.MessageText, []byte(`{"success":true,"op":"subscribe"}`))

		for i := 0; i < 5; i++ {
			frame := `{"topic":"tickers.BTCUSDT","data":{"symbol":"BTCUSDT","lastPrice":"65432.10"},"ts":1725148800000}`
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

func TestBybitAdapter_Name(t *testing.T) {
	a := NewBybitAdapter(Config{})
	if a.Name() != "bybit" {
		t.Fatalf("expected 'bybit', got %q", a.Name())
	}
}

func TestBybitAdapter_ConnectAndRead_DataFlow(t *testing.T) {
	srv := newMockBybitServer(t)
	cfg := Config{Testnet: true, Symbols: []string{"BTCUSDT"}}
	a := NewBybitAdapter(cfg)

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
		if traceID[:6] != "bybit-" {
			t.Fatalf("trace_id missing exchange prefix: %q", traceID)
		}
	}
	a.Close()
}

// D4: Verify subscription state is cached for reconnect recovery
func TestBybitAdapter_SubscriptionState_CachedForReconnect(t *testing.T) {
	srv := newMockBybitServer(t)
	cfg := Config{Testnet: true}
	a := NewBybitAdapter(cfg)

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

	symbols := []string{"BTCUSDT", "ETHUSDT"}
	if err := a.Subscribe(ctx, symbols); err != nil {
		t.Fatalf("Subscribe failed: %v", err)
	}

	// Verify state cached
	a.mu.Lock()
	if len(a.lastSymbols) != 2 {
		a.mu.Unlock()
		t.Fatalf("expected 2 cached symbols, got %d", len(a.lastSymbols))
	}
	if a.lastSymbols[0] != "BTCUSDT" || a.lastSymbols[1] != "ETHUSDT" {
		a.mu.Unlock()
		t.Fatalf("cached symbols mismatch: %v", a.lastSymbols)
	}
	a.mu.Unlock()

	a.Close()
}

// D1: Verify rate limiter prevents burst exceeding limit
func TestBybitAdapter_RateLimiter_Integrated(t *testing.T) {
	a := NewBybitAdapter(Config{Testnet: true})

	// Verify limiter exists and configured
	if a.limiter == nil {
		t.Fatal("rate limiter not initialized")
	}

	// Burst should allow up to bybitSubscribeBurst calls
	allowed := 0
	for i := 0; i < 10; i++ {
		if a.limiter.Allow() {
			allowed++
		}
	}
	if allowed != int(bybitSubscribeBurst) {
		t.Fatalf("expected %d burst allows, got %d", int(bybitSubscribeBurst), allowed)
	}
}

func TestBybitAdapter_ReadFrame_NotConnected(t *testing.T) {
	a := NewBybitAdapter(Config{})
	_, _, err := a.ReadFrame(context.Background())
	if err == nil {
		t.Fatal("expected error when not connected")
	}
}

func TestBybitAdapter_Subscribe_NotConnected(t *testing.T) {
	a := NewBybitAdapter(Config{})
	err := a.Subscribe(context.Background(), []string{"BTCUSDT"})
	if err == nil {
		t.Fatal("expected error when not connected")
	}
}

func TestBybitAdapter_Ping_NotConnected(t *testing.T) {
	a := NewBybitAdapter(Config{})
	err := a.Ping(context.Background())
	if err == nil {
		t.Fatal("expected error when not connected")
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
		t.Fatal("expected false before Connect()")
	}
}
