// MODULE: atlas-ws-ingestion
// GOVERNANCE: Contract test for IPC Writer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml

package ipc

import (
	"encoding/binary"
	"net"
	"path/filepath"
	"testing"
	"time"
)

func TestNewWriter_CreatesInstance(t *testing.T) {
	w := NewWriter("/tmp/test.sock")
	if w == nil {
		t.Fatal("NewWriter returned nil")
	}
	if w.socketPath != "/tmp/test.sock" {
		t.Fatalf("expected socket path /tmp/test.sock, got %s", w.socketPath)
	}
}

func TestWrite_ZeroLengthPayload_Rejected(t *testing.T) {
	w := NewWriter("/tmp/test.sock")
	err := w.Write([]byte{})
	if err == nil {
		t.Fatal("expected error for zero-length payload, got nil")
	}
}

func TestWrite_OversizedPayload_Rejected(t *testing.T) {
	w := NewWriter("/tmp/test.sock")
	big := make([]byte, maxFrameSize+1)
	err := w.Write(big)
	if err == nil {
		t.Fatal("expected error for oversized payload, got nil")
	}
}

func TestSerializeAndDeserialize_RoundTrip(t *testing.T) {
	payload := []byte(`{"type":"trade","symbol":"BTC-USDT","price":65432.10}`)
	frame := SerializeFrame(payload)

	if len(frame) != 4+len(payload) {
		t.Fatalf("frame length mismatch: got %d, want %d", len(frame), 4+len(payload))
	}

	length := binary.BigEndian.Uint32(frame[:4])
	if int(length) != len(payload) {
		t.Fatalf("header length mismatch: got %d, want %d", length, len(payload))
	}

	recovered := frame[4:]
	if string(recovered) != string(payload) {
		t.Fatalf("payload mismatch")
	}
}

func TestWriter_ConnectAndWrite_Integration(t *testing.T) {
	tmpDir := t.TempDir()
	sockPath := filepath.Join(tmpDir, "test.sock")

	listener, err := net.Listen("unix", sockPath)
	if err != nil {
		t.Fatalf("failed to create listener: %v", err)
	}
	defer listener.Close()

	received := make(chan []byte, 1)
	go func() {
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		buf := make([]byte, 4096)
		n, _ := conn.Read(buf)
		received <- buf[:n]
	}()

	w := NewWriter(sockPath)
	if err := w.Connect(); err != nil {
		t.Fatalf("Connect failed: %v", err)
	}
	defer w.Close()

	payload := []byte("test-payload")
	if err := w.Write(payload); err != nil {
		t.Fatalf("Write failed: %v", err)
	}

	select {
	case data := <-received:
		if len(data) < 4 {
			t.Fatal("received data too short")
		}
		length := binary.BigEndian.Uint32(data[:4])
		if int(length) != len(payload) {
			t.Fatalf("length mismatch: got %d, want %d", length, len(payload))
		}
		if string(data[4:4+length]) != string(payload) {
			t.Fatalf("payload mismatch")
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for received data")
	}
}

func TestWriter_Close_Idempotent(t *testing.T) {
	w := NewWriter("/tmp/nonexistent.sock")
	if err := w.Close(); err != nil {
		t.Fatalf("first Close should succeed: %v", err)
	}
	if err := w.Close(); err != nil {
		t.Fatalf("second Close should succeed: %v", err)
	}
}
