// MODULE: atlas-gateway
// GOVERNANCE: Matrix B - Go Transfer Layer
// CONTRACT: Extends Hub with arbitrage path broadcast capability.
// WARNING: No panic. Uses existing Hub.Broadcast() channel pattern.
package feed

import (
	"encoding/json"
	"log/slog"
)

// ArbBroadcastFrame is sent to WS clients when an arbitrage path is detected.
type ArbBroadcastFrame struct {
	Type      string         `json:"type"`
	Path      ArbPathPayload `json:"path"`
	TraceID   string         `json:"trace_id"`
	SourceURI string         `json:"source_uri"`
}

// BroadcastArbPath marshals an arbitrage path and forwards via existing Hub.Broadcast.
func (h *Hub) BroadcastArbPath(path ArbPathPayload, traceID string) {
	frame := ArbBroadcastFrame{
		Type:      "arbitrage_path",
		Path:      path,
		TraceID:   traceID,
		SourceURI: "go-gateway://v1",
	}

	data, err := json.Marshal(frame)
	if err != nil {
		slog.Error("arb_broadcast_marshal_failed",
			"trace_id", traceID,
			"error", err.Error(),
		)
		return
	}

	h.Broadcast(data)
}
