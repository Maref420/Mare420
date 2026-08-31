// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml
// WARNING: This is the SINGLE source of serialization truth for IPC binary v1.
//          Any change requires updating Rust side AND new ADR.

package ipc

import "encoding/binary"

// SerializeFrame produces a length-prefixed binary frame per ipc-binary-v1 spec.
// Format: [4-byte big-endian length][payload]
func SerializeFrame(payload []byte) []byte {
	length := uint32(len(payload))
	frame := make([]byte, 4+int(length))
	binary.BigEndian.PutUint32(frame[:4], length)
	copy(frame[4:], payload)
	return frame
}
