// MODULE: atlas-ws-ingestion
// GOVERNANCE: Data Lifecycle Traceability per ADR-007a + CR-P0-004 Section H
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml (trace_header amendment)
// WARNING: trace_id generated ONCE at INGEST. NEVER modified downstream.

package adapter

import (
	"fmt"
	"sync/atomic"
	"time"
)

// TraceGenerator produces unique, sortable trace IDs per ADR-007a.
// Format: {exchange}-{timestamp_ms}-{sequence}
type TraceGenerator struct {
	exchange string
	seq      atomic.Uint64
}

func NewTraceGenerator(exchange string) *TraceGenerator {
	return &TraceGenerator{exchange: exchange}
}

func (tg *TraceGenerator) Generate() string {
	ts := time.Now().UnixMilli()
	seq := tg.seq.Add(1)
	return fmt.Sprintf("%s-%d-%020d", tg.exchange, ts, seq)
}
