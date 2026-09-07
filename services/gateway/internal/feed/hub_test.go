// MODULE: atlas-gateway
// TEST TYPE: Unit tests for Hub metering integration
package feed

import (
	"testing"
	"time"

	"github.com/atlas-ai/services/gateway/internal/config"
	"github.com/atlas-ai/services/gateway/internal/metering"
)

func TestHub_AttachMeter(t *testing.T) {
	t.Parallel()
	h := NewHub()
	if h.meter != nil {
		t.Fatal("expected nil meter before attach")
	}
	m := metering.NewMeter()
	h.AttachMeter(m)
	if h.meter == nil {
		t.Fatal("expected non-nil meter after attach")
	}
}

func TestHub_DroppedFrameRecordsCustomerDrop(t *testing.T) {
	m := metering.NewMeter()
	h := NewHub()
	h.AttachMeter(m)
	go h.Run()
	defer h.Stop()

	customer := config.CustomerConfig{Name: "drop-test"}
	client := NewClient(customer, h)
	// Buffer of 1 so second broadcast will drop
	client.Send = make(chan []byte, 1)
	h.register <- client
	time.Sleep(50 * time.Millisecond)

	// Fill the buffer
	client.Send <- []byte("first")
	// This should drop because buffer is full
	h.Broadcast([]byte("second"))
	time.Sleep(50 * time.Millisecond)

	stats, ok := m.GetUsage(customer.Name)
	if !ok {
		t.Fatal("expected usage stats for customer")
	}
	if stats.DroppedFrames != 1 {
		t.Errorf("DroppedFrames: want 1, got %d", stats.DroppedFrames)
	}
}
