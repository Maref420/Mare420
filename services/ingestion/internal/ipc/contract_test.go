// MODULE: atlas-ws-ingestion
// GOVERNANCE: Contract test for IPC binary format v1
// ADR: docs/decisions/006-websocket-ingestion-architecture.md

package ipc

import (
	"encoding/binary"
	"testing"
)

func TestFrameSerialization(t *testing.T) {
	payload := []byte(`{"type":"trade","price":100.5}`)
	frame := SerializeFrame(payload)

	if len(frame) < 4 {
		t.Fatal("frame too short: missing length prefix")
	}

	length := binary.BigEndian.Uint32(frame[:4])
	if int(length) != len(payload) {
		t.Fatalf("length mismatch: got %d, want %d", length, len(payload))
	}

	if string(frame[4:]) != string(payload) {
		t.Fatalf("payload mismatch: got %s, want %s", frame[4:], payload)
	}
}

