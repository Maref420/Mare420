// MODULE: atlas-ws-ingestion
// GOVERNANCE: Trace ID generation tests per ADR-007a

package adapter

import (
	"strings"
	"testing"
)

func TestTraceGenerator_Format(t *testing.T) {
	tg := NewTraceGenerator("bybit")
	id := tg.Generate()

	parts := strings.Split(id, "-")
	if len(parts) != 3 {
		t.Fatalf("expected 3 parts in trace_id, got %d: %q", len(parts), id)
	}
	if parts[0] != "bybit" {
		t.Fatalf("expected exchange 'bybit', got %q", parts[0])
	}
}

func TestTraceGenerator_Uniqueness(t *testing.T) {
	tg := NewTraceGenerator("okx")
	seen := make(map[string]bool)
	for i := 0; i < 1000; i++ {
		id := tg.Generate()
		if seen[id] {
			t.Fatalf("duplicate trace_id at iteration %d: %q", i, id)
		}
		seen[id] = true
	}
}

func TestTraceGenerator_Sortability(t *testing.T) {
	tg := NewTraceGenerator("kucoin")
	prev := tg.Generate()
	for i := 0; i < 100; i++ {
		curr := tg.Generate()
		if curr <= prev {
			t.Fatalf("trace_id not sortable: %q <= %q", curr, prev)
		}
		prev = curr
	}
}
