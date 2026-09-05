package main

import (
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"atlas.ai/message-broker/internal/envelope"
	"atlas.ai/message-broker/internal/health"
	"atlas.ai/message-broker/internal/transport"
)

func validEnvelope() []byte {
	return []byte(`{"contract_version":"1.0","message_type":"risk.assessment.v1","source_engine":"rust_engine","timestamp":"2026-08-30T00:00:00Z","payload":{"test":true},"metadata":{"specification_id":"risk-assessment-v1","policy_version":"1.0","owner":"Risk Engine","validation_status":"validated"}}`)
}

func TestValidateValidEnvelope(t *testing.T) {
	msg, err := envelope.Validate(validEnvelope())
	if err != nil {
		t.Fatalf("expected valid envelope, got error: %v", err)
	}
	if msg.ContractVersion != "1.0" {
		t.Errorf("expected contract_version 1.0, got %s", msg.ContractVersion)
	}
	if msg.SourceEngine != "rust_engine" {
		t.Errorf("expected source_engine rust_engine, got %s", msg.SourceEngine)
	}
}

func TestValidateRejectsUnknownFields(t *testing.T) {
	data := []byte(`{"contract_version":"1.0","message_type":"x","source_engine":"rust_engine","timestamp":"2026-01-01T00:00:00Z","payload":{},"metadata":{"specification_id":"s","policy_version":"1.0","owner":"o","validation_status":"v"},"bad_field":true}`)
	_, err := envelope.Validate(data)
	if err == nil {
		t.Fatal("expected error for unknown fields, got nil")
	}
}

func TestValidateRejectsInvalidContractVersion(t *testing.T) {
	data := []byte(`{"contract_version":"2.0","message_type":"x","source_engine":"rust_engine","timestamp":"2026-01-01T00:00:00Z","payload":{},"metadata":{"specification_id":"s","policy_version":"1.0","owner":"o","validation_status":"v"}}`)
	_, err := envelope.Validate(data)
	if err == nil {
		t.Fatal("expected error for invalid contract_version, got nil")
	}
}

func TestValidateRejectsInvalidSourceEngine(t *testing.T) {
	data := []byte(`{"contract_version":"1.0","message_type":"x","source_engine":"java_engine","timestamp":"2026-01-01T00:00:00Z","payload":{},"metadata":{"specification_id":"s","policy_version":"1.0","owner":"o","validation_status":"v"}}`)
	_, err := envelope.Validate(data)
	if err == nil {
		t.Fatal("expected error for invalid source_engine, got nil")
	}
}

func TestValidateRejectsMissingRequiredFields(t *testing.T) {
	data := []byte(`{"contract_version":"1.0","source_engine":"rust_engine","payload":{},"metadata":{"specification_id":"s","policy_version":"1.0","owner":"o","validation_status":"v"}}`)
	_, err := envelope.Validate(data)
	if err == nil {
		t.Fatal("expected error for missing message_type/timestamp, got nil")
	}
}

func TestChannelPublishSubscribe(t *testing.T) {
	tr := transport.NewChannelTransport()
	defer tr.Close()
	received := make(chan []byte, 1)
	err := tr.Subscribe("test.topic", func(data []byte) error {
		received <- data
		return nil
	})
	if err != nil {
		t.Fatalf("subscribe failed: %v", err)
	}
	err = tr.Publish("test.topic", []byte("hello"))
	if err != nil {
		t.Fatalf("publish failed: %v", err)
	}
	msg := <-received
	if string(msg) != "hello" {
		t.Errorf("expected hello, got %s", string(msg))
	}
}

func TestChannelPublishAfterClose(t *testing.T) {
	tr := transport.NewChannelTransport()
	tr.Close()
	err := tr.Publish("test.topic", []byte("hello"))
	if err == nil {
		t.Fatal("expected error publishing after close, got nil")
	}
}

func TestChannelConcurrentPubSub(t *testing.T) {
	tr := transport.NewChannelTransport()
	defer tr.Close()
	var mu sync.Mutex
	count := 0
	for i := 0; i < 10; i++ {
		err := tr.Subscribe("concurrent", func(data []byte) error {
			mu.Lock()
			count++
			mu.Unlock()
			return nil
		})
		if err != nil {
			t.Fatalf("subscribe %d failed: %v", i, err)
		}
	}
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_ = tr.Publish("concurrent", []byte("msg"))
		}()
	}
	wg.Wait()
}

func TestHealthEndpoint(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	health.Handler()(w, req)
	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	if w.Body.String() != `{"status":"ok"}` {
		t.Errorf("unexpected body: %s", w.Body.String())
	}
}
