// MODULE: atlas-gateway
// TEST TYPE: Unit tests for metering.Meter
package metering

import (
	"sync"
	"testing"
)

func TestMeter_RecordFrame_IncrementsCounters(t *testing.T) {
	t.Parallel()
	m := NewMeter()
	m.RecordFrame("cust1", 100, false)
	s, ok := m.GetUsage("cust1")
	if !ok {
		t.Fatal("expected stats to exist")
	}
	if s.FramesTotal != 1 {
		t.Errorf("FramesTotal: want 1, got %d", s.FramesTotal)
	}
	if s.BytesTotal != 100 {
		t.Errorf("BytesTotal: want 100, got %d", s.BytesTotal)
	}
}

func TestMeter_RecordFrame_MultipleCustomers(t *testing.T) {
	t.Parallel()
	m := NewMeter()
	m.RecordFrame("c1", 100, false)
	m.RecordFrame("c2", 200, false)
	s1, _ := m.GetUsage("c1")
	s2, _ := m.GetUsage("c2")
	if s1.BytesTotal != 100 || s2.BytesTotal != 200 {
		t.Error("incorrect byte totals")
	}
}

func TestMeter_GetUsage_ReturnsCopy(t *testing.T) {
	t.Parallel()
	m := NewMeter()
	m.RecordFrame("c1", 100, false)
	s1, _ := m.GetUsage("c1")
	s1.FramesTotal = 999
	s2, _ := m.GetUsage("c1")
	if s2.FramesTotal != 1 {
		t.Error("GetUsage must return copy")
	}
}

func TestMeter_GetAllUsage_Snapshot(t *testing.T) {
	t.Parallel()
	m := NewMeter()
	m.RecordFrame("c1", 100, false)
	snap := m.GetAllUsage()
	delete(snap, "c1")
	if _, ok := m.GetUsage("c1"); !ok {
		t.Error("snapshot mutation affected internal state")
	}
}

func TestMeter_ConcurrentAccess(t *testing.T) {
	t.Parallel()
	m := NewMeter()
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			id := "cust"
			m.RecordFrame(id, 10, false)
			m.GetUsage(id)
		}(i)
	}
	wg.Wait()
	s, ok := m.GetUsage("cust")
	if !ok || s.FramesTotal != 100 {
		t.Errorf("concurrent: want 100 frames, got %d", s.FramesTotal)
	}
}

func TestMeter_ResetCustomer(t *testing.T) {
	t.Parallel()
	m := NewMeter()
	m.RecordFrame("c1", 100, false)
	m.ResetCustomer("c1")
	if _, ok := m.GetUsage("c1"); ok {
		t.Error("expected customer removed after reset")
	}
}

func TestMeter_DroppedFrames(t *testing.T) {
	t.Parallel()
	m := NewMeter()
	m.RecordFrame("c1", 0, true)
	m.RecordFrame("c1", 0, true)
	s, _ := m.GetUsage("c1")
	if s.DroppedFrames != 2 {
		t.Errorf("DroppedFrames: want 2, got %d", s.DroppedFrames)
	}
}
