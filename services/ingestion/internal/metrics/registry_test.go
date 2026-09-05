// MODULE: atlas-ws-ingestion
// GOVERNANCE: Observability Policy - metrics registration MUST be tested
// ADR: docs/decisions/006-websocket-ingestion-architecture.md

package metrics

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus"

	dto "github.com/prometheus/client_model/go"
)

func TestRegister_Idempotent(t *testing.T) {
	// Calling Register() multiple times must NOT panic
	Register()
	Register()
	Register()
}

func TestRegister_AllMetricsCollectable(t *testing.T) {
	Register()

	// Trigger CounterVec lazy initialization by calling WithLabelValues
	// Prometheus only exposes CounterVec metrics after first label access
	FramesDropped.WithLabelValues("test")
	ReconnectionAttempts.WithLabelValues("test")
	ErrorEvents.WithLabelValues("test")

	gatherers := prometheus.Gatherers{prometheus.DefaultGatherer}
	families, err := gatherers.Gather()
	if err != nil {
		t.Fatalf("failed to gather metrics after Register(): %v", err)
	}

	expectedMetrics := map[string]bool{
		"ws_connection_state":            false,
		"ws_frames_received_total":       false,
		"ws_frames_forwarded_total":      false,
		"ws_frames_dropped_total":        false,
		"ws_reconnection_attempts_total": false,
		"ws_ipc_backpressure":            false,
		"ws_heartbeat_failures_total":    false,
		"ws_error_events_total":          false,
	}

	for _, f := range families {
		if _, ok := expectedMetrics[f.GetName()]; ok {
			expectedMetrics[f.GetName()] = true
		}
	}

	for name, found := range expectedMetrics {
		if !found {
			t.Errorf("metric %q not found after Register()", name)
		}
	}
}

func TestMetrics_IncrementAndRead(t *testing.T) {
	Register()

	FramesReceived.Inc()
	FramesForwarded.Inc()
	FramesDropped.WithLabelValues("backpressure").Inc()
	ConnectionState.Set(1)

	m := &dto.Metric{}
	if err := FramesReceived.Write(m); err != nil {
		t.Fatalf("FramesReceived.Write failed: %v", err)
	}
	if m.GetCounter().GetValue() < 1 {
		t.Fatalf("FramesReceived value < 1 after Inc()")
	}
}
