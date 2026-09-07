// MODULE: atlas-gateway
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// CONTRACT: Thread-safe per-customer usage tracking for DaaS billing.
package metering

import (
	"log/slog"
	"sync"
	"time"
)

type UsageStats struct {
	CustomerID    string    `json:"customer_id"`
	FramesTotal   int64     `json:"frames_total"`
	BytesTotal    int64     `json:"bytes_total"`
	LastFrameAt   time.Time `json:"last_frame_at"`
	DroppedFrames int64     `json:"dropped_frames"`
}

type Meter struct {
	mu    sync.RWMutex
	stats map[string]*UsageStats
}

func NewMeter() *Meter {
	return &Meter{
		stats: make(map[string]*UsageStats),
	}
}

func (m *Meter) RecordFrame(customerID string, frameBytes int, dropped bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, exists := m.stats[customerID]
	if !exists {
		s = &UsageStats{CustomerID: customerID}
		m.stats[customerID] = s
	}
	s.FramesTotal++
	if frameBytes > 0 {
		s.BytesTotal += int64(frameBytes)
	}
	s.LastFrameAt = time.Now()
	if dropped {
		s.DroppedFrames++
	}
}

func (m *Meter) GetUsage(customerID string) (UsageStats, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	s, exists := m.stats[customerID]
	if !exists {
		return UsageStats{}, false
	}
	return *s, true
}

func (m *Meter) GetAllUsage() map[string]UsageStats {
	m.mu.RLock()
	defer m.mu.RUnlock()
	snapshot := make(map[string]UsageStats, len(m.stats))
	for k, v := range m.stats {
		snapshot[k] = *v
	}
	return snapshot
}

func (m *Meter) ResetCustomer(customerID string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.stats, customerID)
}

func (m *Meter) RunCleanup(interval time.Duration, done <-chan struct{}) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-done:
			slog.Info("meter_cleanup_stopped")
			return
		case <-ticker.C:
			m.mu.RLock()
			for id, s := range m.stats {
				slog.Info("metering_usage",
					"customer_id", id,
					"frames", s.FramesTotal,
					"bytes", s.BytesTotal,
					"dropped", s.DroppedFrames,
				)
			}
			m.mu.RUnlock()
		}
	}
}
