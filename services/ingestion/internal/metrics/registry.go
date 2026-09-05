// MODULE: atlas-ws-ingestion
// GOVERNANCE: Observability Policy - all metrics defined BEFORE business logic
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// README: services/ingestion/README.md (Observability section)
// WARNING: Adding new metrics after this file is created requires ADR amendment

package metrics

import (
	"sync"

	"github.com/prometheus/client_golang/prometheus"
)

var registerOnce sync.Once

var (
	ConnectionState = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "ws_connection_state",
		Help: "Current WebSocket connection state (0=disconnected, 1=connected, 2=reconnecting, 3=circuit_broken)",
	})

	FramesReceived = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ws_frames_received_total",
		Help: "Total raw WebSocket frames received from source",
	})

	FramesForwarded = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ws_frames_forwarded_total",
		Help: "Total frames successfully written to IPC socket",
	})

	FramesDropped = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ws_frames_dropped_total",
		Help: "Total frames dropped with explicit reason",
	}, []string{"reason"})

	ReconnectionAttempts = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ws_reconnection_attempts_total",
		Help: "Total reconnection attempts with reason",
	}, []string{"reason"})

	IPCBackpressure = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "ws_ipc_backpressure",
		Help: "Current number of buffered frames awaiting IPC write",
	})

	HeartbeatFailures = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ws_heartbeat_failures_total",
		Help: "Total heartbeat/ping timeout events",
	})

	ErrorEvents = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ws_error_events_total",
		Help: "Total error events by type",
	}, []string{"error_type"})
)

// Register registers all ingestion metrics with the default Prometheus registry.
// Safe to call multiple times; uses sync.Once internally.
// MUST be called once at startup before any metric is used.
// Adding new metrics requires updating this function AND the README Observability section.
func Register() {
	registerOnce.Do(func() {
		prometheus.MustRegister(
			ConnectionState,
			FramesReceived,
			FramesForwarded,
			FramesDropped,
			ReconnectionAttempts,
			IPCBackpressure,
			HeartbeatFailures,
			ErrorEvents,
		)
	})
}
