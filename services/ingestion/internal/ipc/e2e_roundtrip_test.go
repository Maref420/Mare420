// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml v1.1
// TEST TYPE: E2E Integration — Go Writer → Unix Socket → Rust Listener → parse_frame
// POLICY: deterministic_execution_required, no parallel paths
// WARNING: Requires atlas-ipc-listener binary at ../../../core_engine/ipc_listener/target/debug/atlas-ipc-listener

package ipc

import (
	"fmt"
	"os"
	"runtime"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

// resolveListenerBinary finds the atlas-ipc-listener binary relative to THIS test file,
// regardless of working directory. Uses runtime.Caller to locate the source file.
func resolveListenerBinary() (string, error) {
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		return "", fmt.Errorf("runtime.Caller failed to determine test file path")
	}
	// filename = .../services/ingestion/internal/ipc/e2e_roundtrip_test.go
	// Go up 4 levels to repo root: ipc/ -> internal/ -> ingestion/ -> services/ -> repo root
	repoRoot := filepath.Dir(filepath.Dir(filepath.Dir(filepath.Dir(filepath.Dir(filename)))))
	binaryPath := filepath.Join(repoRoot, "core_engine", "ipc_listener", "target", "debug", "atlas-ipc-listener")
	return binaryPath, nil
}

// TestE2E_TracedFrameRoundTrip verifies the complete data path:
// Go SerializeFrameTraced → IPC Writer → Unix Socket → Rust atlas-ipc-listener → parse_frame → TraceInfo
func TestE2E_TracedFrameRoundTrip(t *testing.T) {
	// === Step 0: Locate listener binary ===
	binaryPath, err := resolveListenerBinary()
	if err != nil {
		t.Fatalf("failed to resolve listener binary path: %v", err)
	}
	if _, err := os.Stat(binaryPath); err != nil {
		t.Skipf("listener binary not found at %s — run 'cargo build -p atlas-ipc-listener' first", binaryPath)
	}

	// === Step 1: Create unique socket path (parallel-safe) ===
	socketPath := filepath.Join(t.TempDir(), "atlas_e2e.sock")

	// === Step 2: Start Rust listener as subprocess ===
	cmd := exec.Command(binaryPath)
	cmd.Env = append(os.Environ(),
		"WS_IPC_SOCKET_PATH="+socketPath,
		"RUST_LOG=info",
	)
	outputBuf := &strings.Builder{}
	cmd.Stdout = outputBuf
	cmd.Stderr = outputBuf

	if err := cmd.Start(); err != nil {
		t.Fatalf("failed to start listener: %v", err)
	}

	// Guaranteed cleanup: kill process + remove socket
	t.Cleanup(func() {
		if cmd.Process != nil {
			_ = cmd.Process.Signal(syscall.SIGINT)
			done := make(chan struct{})
			go func() { _ = cmd.Wait(); close(done) }()
			select {
			case <-done:
			case <-time.After(5 * time.Second):
				_ = cmd.Process.Kill()
			}
		}
	})

	// === Step 3: Wait for socket to appear (deterministic polling) ===
	socketReady := false
	for i := 0; i < 50; i++ {
		if _, err := os.Stat(socketPath); err == nil {
			socketReady = true
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	if !socketReady {
		t.Fatalf("listener socket not ready after 5s at %s\nlistener output: %s", socketPath, outputBuf.String())
	}

	// === Step 4: Write traced frames via Go Writer ===
	writer := NewWriter(socketPath)
	if err := writer.Connect(); err != nil {
		t.Fatalf("writer connect failed: %v\nlistener output: %s", err, outputBuf.String())
	}

	type testCase struct {
		name     string
		payload  []byte
		traceID  string
		wantTag  string
		wantKind string // "traced" or "legacy"
	}

	cases := []testCase{
		{
			name:     "bybit_ticker",
			payload:  []byte(`{"symbol":"BTCUSDT","price":"74734.50"}`),
			traceID:  "bybit-1788293930811-001",
			wantTag:  "bybit",
			wantKind: "traced",
		},
		{
			name:     "okx_ticker",
			payload:  []byte(`{"instId":"BTC-USDT","last":"74735.00"}`),
			traceID:  "okx-1788293930812-001",
			wantTag:  "okx",
			wantKind: "traced",
		},
		{
			name:     "legacy_no_trace",
			payload:  []byte(`{"legacy":true}`),
			traceID:  "",
			wantTag:  "",
			wantKind: "legacy",
		},
	}

	for _, tc := range cases {
		serialized := SerializeFrameTraced(tc.payload, tc.traceID)
		if err := writer.WriteRaw(serialized); err != nil {
			t.Fatalf("write failed for %s: %v", tc.name, err)
		}
		t.Logf("wrote frame: %s (%d bytes)", tc.name, len(serialized))
	}

	// Allow time for all frames to be flushed through the socket
	// and processed by the listener before closing the connection.
	time.Sleep(200 * time.Millisecond)

	if err := writer.Close(); err != nil {
		t.Fatalf("writer close failed: %v", err)
	}

	// === Step 5: Give listener time to process, then shutdown ===
	time.Sleep(500 * time.Millisecond)
	_ = cmd.Process.Signal(syscall.SIGINT)

	done := make(chan struct{})
	go func() { _ = cmd.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		_ = cmd.Process.Kill()
		t.Fatal("listener did not shutdown within 5s")
	}

	// === Step 6: Structured assertions on listener output ===
	output := outputBuf.String()
	t.Logf("listener output:\n%s", output)

	// Count FRAME RECEIVED lines
	frameCount := strings.Count(output, "FRAME RECEIVED")
	if frameCount != len(cases) {
		t.Errorf("expected %d FRAME RECEIVED logs, got %d", len(cases), frameCount)
	}

	// Verify each traced frame
	for _, tc := range cases {
		if tc.wantKind == "traced" {
			if !strings.Contains(output, `exchange_tag":"`+tc.wantTag+`"`) {
				t.Errorf("missing exchange_tag=%q in listener output", tc.wantTag)
			}
			if !strings.Contains(output, `trace_status":"traced"`) {
				t.Errorf("missing trace_status=traced for %s", tc.name)
			}
		} else {
			if !strings.Contains(output, `trace_status":"legacy"`) {
				t.Errorf("missing trace_status=legacy for %s", tc.name)
			}
		}
	}

	// Verify zero parse errors
	if strings.Contains(output, "frame parse failed") {
		t.Error("listener reported parse failures — check output above")
	}

	// Verify graceful shutdown
	if !strings.Contains(output, "graceful shutdown complete") {
		t.Error("listener did not report graceful shutdown")
	}

	t.Log("E2E ROUNDTRIP TEST: PASSED")
}
