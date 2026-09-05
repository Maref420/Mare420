package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"atlas.ai/message-broker/internal/envelope"
	"atlas.ai/message-broker/internal/transport"
)

// publishHandler replicates the real /publish logic from main.go
// for isolated testing without starting the full server.
func publishHandler(t *testing.T, tr transport.Transport) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
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
			w.WriteHeader(http.StatusBadRequest)
			_, _ = w.Write([]byte(err.Error()))
			return
		}
		if err := tr.Publish(msg.MessageType, body); err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"published"}`))
	}
}

func validEnvelopeJSON() []byte {
	return []byte(`{"contract_version":"1.0","message_type":"exec.order.v1","source_engine":"python_engine","timestamp":"2026-08-30T12:00:00Z","payload":{"symbol":"BTCUSDT","side":"buy","quantity":1.0},"metadata":{"specification_id":"order-v1","policy_version":"1.0","owner":"Python AI Agent","validation_status":"validated"}}`)
}

// === V2: Invalid envelopes are ACTUALLY rejected ===

func TestProdRejectsWrongContractVersion(t *testing.T) {
	tr := transport.NewChannelTransport()
	defer tr.Close()
	srv := httptest.NewServer(publishHandler(t, tr))
	defer srv.Close()
	body := []byte(`{"contract_version":"2.0","message_type":"x","source_engine":"rust_engine","timestamp":"2026-01-01T00:00:00Z","payload":{},"metadata":{"specification_id":"s","policy_version":"1.0","owner":"o","validation_status":"v"}}`)
	resp, err := http.Post(srv.URL+"/publish", "application/json", bytes.NewReader(body))
	if err != nil { t.Fatalf("request failed: %v", err) }
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("expected 400 for wrong contract_version, got %d", resp.StatusCode)
	}
}

func TestProdRejectsUnauthorizedEngine(t *testing.T) {
	tr := transport.NewChannelTransport()
	defer tr.Close()
	srv := httptest.NewServer(publishHandler(t, tr))
	defer srv.Close()
	body := []byte(`{"contract_version":"1.0","message_type":"x","source_engine":"java_engine","timestamp":"2026-01-01T00:00:00Z","payload":{},"metadata":{"specification_id":"s","policy_version":"1.0","owner":"o","validation_status":"v"}}`)
	resp, _ := http.Post(srv.URL+"/publish", "application/json", bytes.NewReader(body))
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("expected 400 for unauthorized engine, got %d", resp.StatusCode)
	}
}

func TestProdRejectsMissingMetadataFields(t *testing.T) {
	tr := transport.NewChannelTransport()
	defer tr.Close()
	srv := httptest.NewServer(publishHandler(t, tr))
	defer srv.Close()
	body := []byte(`{"contract_version":"1.0","message_type":"x","source_engine":"go_engine","timestamp":"2026-01-01T00:00:00Z","payload":{},"metadata":{"specification_id":"s"}}`)
	resp, _ := http.Post(srv.URL+"/publish", "application/json", bytes.NewReader(body))
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("expected 400 for missing metadata fields, got %d", resp.StatusCode)
	}
}



// === V4: No panic or data corruption during shutdown under load ===

func TestProdGracefulShutdownUnderLoad(t *testing.T) {
	tr := transport.NewChannelTransport()
	var wg sync.WaitGroup
	stopCh := make(chan struct{})

	// Start 10 publishers hammering the transport
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				select {
				case <-stopCh:
					return
				default:
					_ = tr.Publish("shutdown.test", []byte("msg"))
				}
			}
		}()
	}

	// Let it run briefly then close
	time.Sleep(50 * time.Millisecond)
	close(stopCh)
	err := tr.Close()
	if err != nil {
		t.Errorf("Close() returned error during active publishing: %v", err)
	}
	wg.Wait()

	// Verify post-close publish returns error (not panic)
	err = tr.Publish("shutdown.test", []byte("after-close"))
	if err == nil {
		t.Error("Publish after Close MUST return error, not succeed silently")
	}
}

// === V6: Error responses are structured and informative ===

func TestProdErrorResponseBodyIsReadable(t *testing.T) {
	tr := transport.NewChannelTransport()
	defer tr.Close()
	srv := httptest.NewServer(publishHandler(t, tr))
	defer srv.Close()
	// Send completely invalid JSON
	resp, err := http.Post(srv.URL+"/publish", "application/json", bytes.NewReader([]byte("{invalid")))
	if err != nil { t.Fatalf("request failed: %v", err) }
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", resp.StatusCode)
	}
	body, _ := io.ReadAll(resp.Body)
	if len(body) == 0 {
		t.Error("error response body MUST NOT be empty — client needs diagnostic info")
	}
}

func TestProdMethodNotAllowed(t *testing.T) {
	tr := transport.NewChannelTransport()
	defer tr.Close()
	srv := httptest.NewServer(publishHandler(t, tr))
	defer srv.Close()
	resp, _ := http.Get(srv.URL + "/publish")
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("GET /publish must return 405, got %d", resp.StatusCode)
	}
}

// === V3: Concurrent stress — 50 clients, 20 messages each ===
// Buffer=1024 absorbs 1000 messages. Overflow returns explicit error.

func TestProdConcurrentStress(t *testing.T) {
	tr := transport.NewChannelTransport()
	defer tr.Close()
	var received int64
	var mu sync.Mutex
	err := tr.Subscribe("stress.test", func(data []byte) error {
		mu.Lock()
		received++
		mu.Unlock()
		return nil
	})
	if err != nil { t.Fatalf("subscribe failed: %v", err) }

	const clients = 50
	const msgsPerClient = 20
	var wg sync.WaitGroup
	var publishErrors int64
	var errMu sync.Mutex
	for c := 0; c < clients; c++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			for m := 0; m < msgsPerClient; m++ {
				payload := map[string]interface{}{"client": id, "msg": m}
				data, _ := json.Marshal(payload)
				if err := tr.Publish("stress.test", data); err != nil {
					errMu.Lock()
					publishErrors++
					errMu.Unlock()
				}
			}
		}(c)
	}
	wg.Wait()
	time.Sleep(200 * time.Millisecond)
	mu.Lock()
	finalCount := received
	mu.Unlock()
	expected := int64(clients * msgsPerClient)
	totalAccounted := finalCount + publishErrors
	if totalAccounted != expected {
		t.Errorf("messages lost: sent=%d received=%d errors=%d unaccounted=%d",
			expected, finalCount, publishErrors, expected-totalAccounted)
	}
	if finalCount != expected {
		t.Logf("NOTE: %d messages returned ErrBufferFull (backpressure working correctly)", publishErrors)
	}
	// Key assertion: NO silent data loss. Every message either delivered or errored.
	if totalAccounted == expected {
		t.Logf("✅ Zero silent data loss: %d delivered + %d backpressured = %d total", finalCount, publishErrors, expected)
	}
}
