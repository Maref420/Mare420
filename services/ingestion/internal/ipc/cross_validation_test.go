// MODULE: atlas-ws-ingestion
// GOVERNANCE: Cross-language contract validation for IPC binary format v1
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml
// WARNING: This test generates golden fixtures consumed by Rust tests.
//          Changing serialization format here REQUIRES updating Rust side AND new ADR.

package ipc

import (
	"encoding/binary"
	"os"
	"path/filepath"
	"testing"
)

const goldenDir = "../../testdata/ipc_frames"

// SerializeFrame produces a length-prefixed binary frame per ipc-binary-v1 spec.
// Format: [4-byte big-endian length][payload]
// This is the SINGLE source of serialization truth for Go side.

// generateGoldenFixtures creates .bin files that Rust tests consume.
// Run with: go test -run TestGenerateGoldenFixtures -v
func TestGenerateGoldenFixtures(t *testing.T) {
	if err := os.MkdirAll(goldenDir, 0o755); err != nil {
		t.Fatalf("failed to create golden dir: %v", err)
	}

	fixtures := map[string][]byte{
		"valid_trade_frame.bin":      SerializeFrame([]byte(`{"type":"trade","symbol":"BTC-USDT","price":65432.10,"size":0.5,"ts_event":1725148800000000000}`)),
		"valid_quote_frame.bin":      SerializeFrame([]byte(`{"type":"quote","symbol":"ETH-USDT","bid":2345.67,"ask":2345.90,"ts_event":1725148800000000000}`)),
		"minimum_one_byte.bin":       SerializeFrame([]byte("x")),
		"large_payload_1mb.bin":      SerializeFrame(make([]byte, 1048576)),
		"unicode_payload.bin":        SerializeFrame([]byte(`{"symbol":"テスト","type":"trade"}`)),
		"empty_json_object.bin":      SerializeFrame([]byte("{}")),
		"binary_content.bin":         SerializeFrame([]byte{0x00, 0xFF, 0x01, 0xFE, 0x80, 0x7F}),
	}

	for name, frame := range fixtures {
		path := filepath.Join(goldenDir, name)
		if err := os.WriteFile(path, frame, 0o644); err != nil {
			t.Fatalf("failed to write golden fixture %s: %v", name, err)
		}
		t.Logf("generated: %s (%d bytes)", name, len(frame))
	}

	t.Logf("all golden fixtures written to %s", goldenDir)
}

func TestSerializeFrame_ValidPayload(t *testing.T) {
	payload := []byte(`{"type":"trade","price":100.5}`)
	frame := SerializeFrame(payload)

	if len(frame) != 4+len(payload) {
		t.Fatalf("frame length mismatch: got %d, want %d", len(frame), 4+len(payload))
	}

	length := binary.BigEndian.Uint32(frame[:4])
	if int(length) != len(payload) {
		t.Fatalf("header length mismatch: got %d, want %d", length, len(payload))
	}

	if string(frame[4:]) != string(payload) {
		t.Fatalf("payload mismatch: got %q, want %q", frame[4:], payload)
	}
}

func TestSerializeFrame_OneBytePayload(t *testing.T) {
	frame := SerializeFrame([]byte("x"))
	length := binary.BigEndian.Uint32(frame[:4])
	if length != 1 {
		t.Fatalf("expected length 1, got %d", length)
	}
	if frame[4] != 'x' {
		t.Fatalf("expected payload 'x', got %q", frame[4])
	}
}

func TestSerializeFrame_EmptyPayloadProducesZeroLength(t *testing.T) {
	frame := SerializeFrame([]byte{})
	length := binary.BigEndian.Uint32(frame[:4])
	if length != 0 {
		t.Fatalf("empty payload should produce length 0, got %d", length)
	}
	// Note: zero-length frames are REJECTED by Rust deserializer per spec.
	// This test documents Go behavior; Rust side enforces the constraint.
}

func TestSerializeFrame_RoundTrip(t *testing.T) {
	testCases := [][]byte{
		[]byte("hello"),
		[]byte(`{"type":"trade","symbol":"BTC-USDT","price":65432.10}`),
		[]byte{0x00, 0xFF, 0x01},
		make([]byte, 10000),
	}

	for i, original := range testCases {
		frame := SerializeFrame(original)
		length := binary.BigEndian.Uint32(frame[:4])
		recovered := frame[4 : 4+length]

		if len(recovered) != len(original) {
			t.Fatalf("case %d: length mismatch after round-trip: got %d, want %d", i, len(recovered), len(original))
		}
		for j := range original {
			if recovered[j] != original[j] {
				t.Fatalf("case %d: byte mismatch at offset %d: got 0x%02x, want 0x%02x", i, j, recovered[j], original[j])
			}
		}
	}
}

