// MODULE: atlas-ws-ingestion
// GOVERNANCE: Trace-aware IPC frame serialization tests per CR-P0-004 Section H
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml v1.1 trace header amendment

package ipc

import (
	"encoding/binary"
	"testing"
)

func TestSerializeFrameTraced_WithValidTraceID(t *testing.T) {
	payload := []byte(`{"type":"trade","price":100.5}`)
	traceID := "bybit-1788293930811-00000000000000000001"

	frame := SerializeFrameTraced(payload, traceID)

	// Minimum frame size: 4 (length) + 1 (flags) + 8 (ts) + 1 (tag_len) + 5 ("bybit") + len(payload)
	minSize := 4 + 1 + 8 + 1 + 5 + len(payload)
	if len(frame) < minSize {
		t.Fatalf("frame too short: got %d, want >= %d", len(frame), minSize)
	}

	// Check length header
	totalLen := binary.BigEndian.Uint32(frame[:4])
	if int(totalLen) != len(frame)-4 {
		t.Fatalf("length header mismatch: header says %d, actual payload after header is %d", totalLen, len(frame)-4)
	}

	// Check flags byte
	flags := frame[4]
	if flags != flagTracePresent {
		t.Fatalf("flags byte should be 0x%02x, got 0x%02x", flagTracePresent, flags)
	}

	// Check timestamp
	tsMs := binary.BigEndian.Uint64(frame[5:13])
	if tsMs != 1788293930811 {
		t.Fatalf("timestamp mismatch: got %d, want 1788293930811", tsMs)
	}

	// Check exchange tag
	tagLen := int(frame[13])
	if tagLen != 5 {
		t.Fatalf("tag length should be 5 (bybit), got %d", tagLen)
	}
	tag := string(frame[14 : 14+tagLen])
	if tag != "bybit" {
		t.Fatalf("exchange tag should be 'bybit', got %q", tag)
	}

	// Check payload starts after trace fields
	payloadOffset := 14 + tagLen
	recovered := frame[payloadOffset:]
	if string(recovered) != string(payload) {
		t.Fatalf("payload mismatch: got %q, want %q", recovered, payload)
	}
}

func TestSerializeFrameTraced_EmptyTraceID_FallsBackToLegacy(t *testing.T) {
	payload := []byte(`{"type":"trade","price":100.5}`)
	frame := SerializeFrameTraced(payload, "")

	// Should be: [4-byte length][1-byte flags=0x00][payload]
	expectedLen := 4 + 1 + len(payload)
	if len(frame) != expectedLen {
		t.Fatalf("frame length mismatch: got %d, want %d", len(frame), expectedLen)
	}

	flags := frame[4]
	if flags != 0x00 {
		t.Fatalf("flags should be 0x00 for empty traceID, got 0x%02x", flags)
	}

	recovered := frame[5:]
	if string(recovered) != string(payload) {
		t.Fatalf("payload mismatch: got %q, want %q", recovered, payload)
	}
}

func TestSerializeFrameTraced_MalformedTraceID_FallsBackToLegacy(t *testing.T) {
	payload := []byte(`{"data":"test"}`)

	malformedIDs := []string{
		"no-dashes-here",
		"only-one-dash",
		"bybit-notanumber-seq",
		"",
	}

	for _, traceID := range malformedIDs {
		frame := SerializeFrameTraced(payload, traceID)
		flags := frame[4]
		if flags != 0x00 {
			t.Errorf("malformed traceID %q should produce flags=0x00, got 0x%02x", traceID, flags)
		}
	}
}

func TestSerializeFrameTraced_OKXTraceID(t *testing.T) {
	payload := []byte(`{"instId":"BTC-USDT","last":"65432.1"}`)
	traceID := "okx-1788293930811-00000000000000000042"

	frame := SerializeFrameTraced(payload, traceID)

	flags := frame[4]
	if flags != flagTracePresent {
		t.Fatalf("flags should be 0x%02x, got 0x%02x", flagTracePresent, flags)
	}

	tsMs := binary.BigEndian.Uint64(frame[5:13])
	if tsMs != 1788293930811 {
		t.Fatalf("timestamp mismatch: got %d", tsMs)
	}

	tagLen := int(frame[13])
	tag := string(frame[14 : 14+tagLen])
	if tag != "okx" {
		t.Fatalf("exchange tag should be 'okx', got %q", tag)
	}

	payloadOffset := 14 + tagLen
	if string(frame[payloadOffset:]) != string(payload) {
		t.Fatalf("payload mismatch")
	}
}

func TestSerializeFrameTraced_LongExchangeTag_Truncated(t *testing.T) {
	payload := []byte("data")
	// Exchange tag longer than 32 bytes but NO dashes (so parseTraceID succeeds)
	// Format: {exchange}-{timestamp_ms}-{sequence}
	longExchange := "thisisaverylongexchangenamethatexceedsthelimit" // 47 chars, no dashes
	traceID := longExchange + "-1788293930811-00000000000000000001"

	frame := SerializeFrameTraced(payload, traceID)

	// Verify it's in traced format (flags=0x01)
	flags := frame[4]
	if flags != flagTracePresent {
		t.Fatalf("expected traced format (flags=0x%02x), got 0x%02x — parseTraceID may have failed", flagTracePresent, flags)
	}

	tagLen := int(frame[13])
	if tagLen > maxExchangeTag {
		t.Fatalf("tag length should be truncated to %d, got %d", maxExchangeTag, tagLen)
	}
	if tagLen != maxExchangeTag {
		t.Fatalf("tag length should be exactly %d after truncation, got %d", maxExchangeTag, tagLen)
	}

	// Verify truncated tag content
	tag := string(frame[14 : 14+tagLen])
	expectedPrefix := longExchange[:maxExchangeTag]
	if tag != expectedPrefix {
		t.Fatalf("truncated tag mismatch: got %q, want %q", tag, expectedPrefix)
	}
}

func TestSerializeFrame_LegacyUnchanged(t *testing.T) {
	// Verify original SerializeFrame is completely unchanged
	payload := []byte(`{"type":"trade","price":100.5}`)
	frame := SerializeFrame(payload)

	if len(frame) != 4+len(payload) {
		t.Fatalf("legacy frame length changed: got %d, want %d", len(frame), 4+len(payload))
	}

	length := binary.BigEndian.Uint32(frame[:4])
	if int(length) != len(payload) {
		t.Fatalf("legacy length header changed: got %d, want %d", length, len(payload))
	}

	if string(frame[4:]) != string(payload) {
		t.Fatalf("legacy payload changed")
	}
}

func TestParseTraceID_Valid(t *testing.T) {
	tests := []struct {
		traceID  string
		exchange string
		tsMs     uint64
	}{
		{"bybit-1788293930811-00000000000000000001", "bybit", 1788293930811},
		{"okx-1788293930811-00000000000000000042", "okx", 1788293930811},
		{"hyperliquid-1788293930811-1", "hyperliquid", 1788293930811},
	}

	for _, tt := range tests {
		exchange, tsMs, err := parseTraceID(tt.traceID)
		if err != nil {
			t.Errorf("parseTraceID(%q) unexpected error: %v", tt.traceID, err)
			continue
		}
		if exchange != tt.exchange {
			t.Errorf("parseTraceID(%q) exchange = %q, want %q", tt.traceID, exchange, tt.exchange)
		}
		if tsMs != tt.tsMs {
			t.Errorf("parseTraceID(%q) tsMs = %d, want %d", tt.traceID, tsMs, tt.tsMs)
		}
	}
}

func TestParseTraceID_Invalid(t *testing.T) {
	invalidIDs := []string{
		"",
		"nodashes",
		"one-dash",
		"bybit-abc-seq",
	}

	for _, id := range invalidIDs {
		_, _, err := parseTraceID(id)
		if err == nil {
			t.Errorf("parseTraceID(%q) should return error, got nil", id)
		}
	}
}
