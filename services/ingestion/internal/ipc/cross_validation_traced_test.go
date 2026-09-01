// MODULE: atlas-ws-ingestion
// GOVERNANCE: Cross-validation Go→Rust for traced IPC frames per CR-P0-004 Section H
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml v1.1

package ipc

import (
	"os"
	"path/filepath"
	"testing"
)

const tracedGoldenDir = "../../testdata/ipc_frames_traced"

func TestGenerateTracedGoldenFixtures(t *testing.T) {
	if err := os.MkdirAll(tracedGoldenDir, 0755); err != nil {
		t.Fatalf("failed to create traced golden dir: %v", err)
	}

	type testCase struct {
		name    string
		payload []byte
		traceID string
	}

	cases := []testCase{
		{
			name:    "bybit_ticker_traced.bin",
			payload: []byte(`{"topic":"tickers.BTCUSDT","ts":1788293930502,"type":"snapshot","data":{"symbol":"BTCUSDT","lastPrice":"74734"}}`),
			traceID: "bybit-1788293930811-00000000000000000001",
		},
		{
			name:    "okx_ticker_traced.bin",
			payload: []byte(`{"instId":"BTC-USDT","last":"65432.1","ts":"1788293930811"}`),
			traceID: "okx-1788293930811-00000000000000000042",
		},
		{
			name:    "legacy_no_trace.bin",
			payload: []byte(`{"type":"trade","price":100.5}`),
			traceID: "", // empty → legacy format
		},
		{
			name:    "bybit_large_payload_traced.bin",
			payload: make([]byte, 10000), // 10KB payload
			traceID: "bybit-1788293930811-00000000000000000100",
		},
		{
			name:    "minimum_traced.bin",
			payload: []byte("x"),
			traceID: "test-1788293930811-1",
		},
	}

	for _, tc := range cases {
		frame := SerializeFrameTraced(tc.payload, tc.traceID)
		path := filepath.Join(tracedGoldenDir, tc.name)
		if err := os.WriteFile(path, frame, 0644); err != nil {
			t.Fatalf("failed to write %s: %v", tc.name, err)
		}
		t.Logf("generated: %s (%d bytes)", tc.name, len(frame))
	}

	t.Logf("all traced golden fixtures written to %s", tracedGoldenDir)
}
