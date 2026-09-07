// MODULE: atlas-gateway
// GOVERNANCE: Matrix B - Go Transfer Layer
// CONTRACT: Receives IpcMessage from Rust ArbOrchestrator, forwards to Hub.
// WARNING: No panic. All errors returned via %w wrapping.
package feed

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
)

// ArbPathPayload matches Rust arb_graph::mapper::ArbitragePath JSON output.
type ArbPathPayload struct {
	Exchanges   []string `json:"exchanges"`
	Symbol      string   `json:"symbol"`
	NetWeight   float64  `json:"net_weight"`
	HopCount    int      `json:"hop_count"`
	Profitable  bool     `json:"profitable"`
	TimestampNs int64    `json:"timestamp_ns"`
	SourceURI   string   `json:"source_uri"`
}

// IpcMessage matches Rust arb_orchestrator::IpcMessage JSON envelope.
type IpcMessage struct {
	MsgType     string          `json:"msg_type"`
	Payload     json.RawMessage `json:"payload"`
	TraceID     string          `json:"trace_id"`
	TimestampNs int64           `json:"timestamp_ns"`
	SourceURI   string          `json:"source_uri"`
}

// HandleArbitragePath parses an IpcMessage and forwards the arbitrage path to the Hub.
func HandleArbitragePath(ctx context.Context, msg IpcMessage, hub *Hub) error {
	if ctx.Err() != nil {
		return fmt.Errorf("context cancelled: %w", ctx.Err())
	}

	if msg.MsgType != "arbitrage_path" {
		return fmt.Errorf("unexpected msg_type: %s", msg.MsgType)
	}

	var payload ArbPathPayload
	if err := json.Unmarshal(msg.Payload, &payload); err != nil {
		return fmt.Errorf("unmarshal arb_path payload: %w", err)
	}

	if payload.Symbol == "" {
		return fmt.Errorf("empty symbol in arb_path")
	}
	if len(payload.Exchanges) < 2 {
		return fmt.Errorf("arb_path requires at least 2 exchanges, got %d", len(payload.Exchanges))
	}
	if payload.SourceURI == "" {
		return fmt.Errorf("empty source_uri in arb_path per ADR-006")
	}

	slog.Info("arb_path_received",
		"trace_id", msg.TraceID,
		"symbol", payload.Symbol,
		"exchanges", payload.Exchanges,
		"net_weight", payload.NetWeight,
		"profitable", payload.Profitable,
		"source_uri", msg.SourceURI,
	)

	hub.BroadcastArbPath(payload, msg.TraceID)

	return nil
}
