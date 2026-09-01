// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml (v1.1 with trace header amendment)
// WARNING: NEVER silently drop frames. Backpressure must be explicit and observable.
// TRACE: Per CR-P0-004 Section H, trace_id propagates through IPC when available.
//        Legacy SerializeFrame remains UNCHANGED for backward compatibility.

package ipc

import (
	"encoding/binary"
	"fmt"
	"strings"
	"time"
)

const (
	flagTracePresent = 0x01 // bit 0 of flags byte
	maxExchangeTag   = 32   // max bytes for exchange tag per spec
)

// SerializeFrame produces a length-prefixed binary frame per ipc-binary-v1 spec (legacy).
// Format: [4-byte big-endian length][payload]
// This function is IMMUTABLE — used by all existing tests and Rust deserializer.
func SerializeFrame(payload []byte) []byte {
	length := uint32(len(payload))
	frame := make([]byte, 4+int(length))
	binary.BigEndian.PutUint32(frame[:4], length)
	copy(frame[4:], payload)
	return frame
}

// SerializeFrameTraced produces a trace-aware frame per ipc-binary-v1 spec v1.1.
// Format when traceID is non-empty:
//   [4-byte BE total_length][1-byte flags=0x01][8-byte BE timestamp_ms][1-byte tag_len][tag_bytes][payload]
// Format when traceID is empty (fallback to legacy):
//   [4-byte BE total_length][1-byte flags=0x00][payload]
//
// traceID format expected: "{exchange}-{timestamp_ms}-{sequence}" e.g. "bybit-1788293930811-00000000000000000001"
// If traceID is empty or malformed, falls back to legacy-compatible format (flags=0x00).
func SerializeFrameTraced(payload []byte, traceID string) []byte {
	if traceID == "" {
		// Fallback: legacy format with flags=0x00
		// Total payload after length header = 1 (flags) + len(payload)
		totalLen := uint32(1 + len(payload))
		frame := make([]byte, 4+int(totalLen))
		binary.BigEndian.PutUint32(frame[:4], totalLen)
		frame[4] = 0x00 // flags: no trace
		copy(frame[5:], payload)
		return frame
	}

	// Parse traceID: "{exchange}-{timestamp_ms}-{sequence}"
	exchange, tsMs, err := parseTraceID(traceID)
	if err != nil {
		// Malformed traceID: fallback to legacy-compatible (flags=0x00)
		totalLen := uint32(1 + len(payload))
		frame := make([]byte, 4+int(totalLen))
		binary.BigEndian.PutUint32(frame[:4], totalLen)
		frame[4] = 0x00
		copy(frame[5:], payload)
		return frame
	}

	// Truncate exchange tag if needed
	tag := exchange
	if len(tag) > maxExchangeTag {
		tag = tag[:maxExchangeTag]
	}

	// Calculate total length after the 4-byte header:
	// 1 (flags) + 8 (timestamp) + 1 (tag_len) + len(tag) + len(payload)
	traceFieldsLen := 1 + 8 + 1 + len(tag)
	totalLen := uint32(traceFieldsLen + len(payload))

	frame := make([]byte, 4+int(totalLen))
	binary.BigEndian.PutUint32(frame[:4], totalLen)

	offset := 4
	frame[offset] = flagTracePresent // flags: trace present
	offset++

	binary.BigEndian.PutUint64(frame[offset:offset+8], tsMs)
	offset += 8

	frame[offset] = byte(len(tag))
	offset++

	copy(frame[offset:offset+len(tag)], tag)
	offset += len(tag)

	copy(frame[offset:], payload)
	return frame
}

// parseTraceID extracts exchange name and timestamp from traceID.
// Expected format: "{exchange}-{timestamp_ms}-{sequence}"
// Returns (exchange, timestamp_ms_uint64, error)
func parseTraceID(traceID string) (string, uint64, error) {
	parts := strings.SplitN(traceID, "-", 3)
	if len(parts) < 3 {
		return "", 0, fmt.Errorf("traceID must have format {exchange}-{ts}-{seq}, got %q", traceID)
	}

	exchange := parts[0]
	tsStr := parts[1]

	var tsMs uint64
	for _, c := range tsStr {
		if c < '0' || c > '9' {
			return "", 0, fmt.Errorf("timestamp must be numeric, got %q in %q", tsStr, traceID)
		}
		tsMs = tsMs*10 + uint64(c-'0')
	}

	if tsMs == 0 {
		// Fallback to current time if parsing yields 0
		tsMs = uint64(time.Now().UnixMilli())
	}

	return exchange, tsMs, nil
}
