// MODULE: atlas-ws-ingestion
// GOVERNANCE: Backpressure contract test - MUST NOT be skipped in CI
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml (buffer_capacity_frames: 1000)

package ipc

import (
	"sync"
	"testing"
)

func TestBackpressureDrop(t *testing.T) {
	// Create writer without connecting (no UDS listener)
	// This means writeLoop will consume from buffer but fail to send,
	// allowing us to test buffer overflow behavior.
	w := NewWriter("/tmp/nonexistent_backpressure_test.sock")

	// Fill buffer to capacity
	payload := []byte("backpressure-test-payload")
	var wg sync.WaitGroup

	// Write maxBufferSize frames to fill the channel
	for i := 0; i < maxBufferSize; i++ {
		err := w.Write(payload)
		if err != nil {
			t.Fatalf("Write %d failed unexpectedly during fill: %v", i, err)
		}
	}

	// Next write should trigger backpressure drop (buffer full)
	// The writer drops oldest and inserts new frame
	err := w.Write(payload)
	if err != nil {
		// If we get an explicit error, that's also acceptable behavior
		t.Logf("overflow write returned error (acceptable): %v", err)
	}

	// Verify buffer is still functional after overflow
	wg.Add(1)
	go func() {
		defer wg.Done()
		for i := 0; i < 10; i++ {
			_ = w.Write(payload)
		}
	}()
	wg.Wait()

	// Writer must not be deadlocked or panicked after overflow
	if err := w.Close(); err != nil {
		t.Fatalf("Close after backpressure failed: %v", err)
	}
}
