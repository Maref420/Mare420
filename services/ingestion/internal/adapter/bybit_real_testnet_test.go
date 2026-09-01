// MODULE: atlas-ws-ingestion
// GOVERNANCE: Real testnet integration test per CR-P0-004 v3 Section F3
// CREDENTIALS: Loaded from env vars ONLY. NEVER hardcoded (C2).
// RUN: BYBIT_TESTNET_KEY=xxx BYBIT_TESTNET_SECRET=yyy go test -v -run TestBybitRealTestnet -timeout 60s
// WARNING: This test connects to REAL Bybit testnet. Requires valid credentials.

package adapter

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/atlas-ai/services/ingestion/internal/metrics"
)

func TestBybitRealTestnet(t *testing.T) {
	apiKey := os.Getenv("BYBIT_TESTNET_KEY")
	apiSecret := os.Getenv("BYBIT_TESTNET_SECRET")

	if apiKey == "" || apiSecret == "" {
		t.Skip("skipping real testnet test: BYBIT_TESTNET_KEY and BYBIT_TESTNET_SECRET required")
	}

	// Initialize metrics registry for this test
	metrics.Register()

	cfg := Config{
		APIKey:    apiKey,
		APISecret: apiSecret,
		Testnet:   true,
		Symbols:   []string{"BTCUSDT"},
	}

	adapter := NewBybitAdapter(cfg)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// === STAGE 1: INGEST - Connect ===
	slog.Info("=== STAGE 1: INGEST - Connecting to Bybit Testnet ===")
	if err := adapter.Connect(ctx); err != nil {
		t.Fatalf("Connect failed: %v", err)
	}
	defer adapter.Close()
	slog.Info("Connected successfully", "exchange", adapter.Name(), "testnet", true)

	// === STAGE 2: INGEST - Subscribe ===
	slog.Info("=== STAGE 2: INGEST - Subscribing to BTCUSDT ===")
	if err := adapter.Subscribe(ctx, cfg.Symbols); err != nil {
		t.Fatalf("Subscribe failed: %v", err)
	}
	slog.Info("Subscribed successfully", "symbols", cfg.Symbols)

	// === STAGE 3: DATA FLOW - Read frames with trace IDs ===
	slog.Info("=== STAGE 3: DATA FLOW - Reading frames (30s window) ===")
	frameCount := 0
	traceIDs := make([]string, 0, 100)
	startTime := time.Now()

	for {
		select {
		case <-ctx.Done():
			goto done
		default:
		}

		frame, traceID, err := adapter.ReadFrame(ctx)
		if err != nil {
			slog.Error("ReadFrame error", "error", err, "frames_received", frameCount)
			break
		}

		frameCount++
		traceIDs = append(traceIDs, traceID)

		// Print data path for first 5 frames
		if frameCount <= 5 {
			slog.Info("FRAME RECEIVED",
				"stage", "INGEST",
				"trace_id", traceID,
				"size_bytes", len(frame),
				"preview", safePreview(frame),
				"path", "Bybit WS → Go Adapter.ReadFrame() → [IPC Write next]",
			)
		}

		// Send periodic ping to keep connection alive
		if frameCount%50 == 0 {
			if err := adapter.Ping(ctx); err != nil {
				slog.Warn("Ping failed", "error", err)
			}
		}
	}

done:
	elapsed := time.Since(startTime)

	// === STAGE 4: OBSERVABILITY - Metrics Summary ===
	slog.Info("=== STAGE 4: OBSERVABILITY - Session Summary ===",
		"total_frames", frameCount,
		"duration_sec", elapsed.Seconds(),
		"fps", float64(frameCount)/elapsed.Seconds(),
		"first_trace_id", firstOrEmpty(traceIDs),
		"last_trace_id", lastOrEmpty(traceIDs),
	)

	// === STAGE 5: DATA PATH VERIFICATION ===
	slog.Info("=== STAGE 5: DATA PATH VERIFICATION ===")

	if frameCount == 0 {
		t.Fatal("received 0 frames in 30 seconds - data flow broken")
	}

	// Verify trace IDs are unique and properly formatted
	seen := make(map[string]bool)
	for _, id := range traceIDs {
		if seen[id] {
			t.Fatalf("duplicate trace_id detected: %s", id)
		}
		seen[id] = true
		if len(id) < 10 || id[:6] != "bybit-" {
			t.Fatalf("invalid trace_id format: %s", id)
		}
	}

	slog.Info("DATA PATH VERIFIED",
		"unique_trace_ids", len(seen),
		"all_formatted_correctly", true,
		"data_flow", "Bybit WS → Go Adapter → trace_id generated → ready for IPC → Rust Normalizer (P2)",
	)

	// === CURRENT ARCHITECTURE VISIBILITY ===
	slog.Info("=== CURRENT DATA PATH MAP ===")
	slog.Info("PATH",
		"stage_1_INGEST", fmt.Sprintf("Bybit Testnet WS → BybitAdapter.ReadFrame() → %d frames with trace_ids", frameCount),
		"stage_2_IPC_WRITE", "Go IPC Writer → Unix Domain Socket (implemented, not wired to adapter yet)",
		"stage_3_VALIDATE", "Rust Frame Validator → accept/quarantine/reject (P2)",
		"stage_4_NORMALIZE", "Rust Normalizer → NormalizedTick with trace_id (P2)",
		"stage_5_DISTRIBUTE", "Rust Distributor → Python Agent / Warm Storage (P3-P4)",
		"stage_6_CONSUME", "Python Agent decision engine (P4)",
		"gap", "Stages 2-6 require wiring adapter output to IPC writer, then Rust pipeline",
	)

	slog.Info("TEST PASSED",
		"frames", frameCount,
		"trace_ids_verified", len(seen),
		"next_step", "Wire adapter.ReadFrame() → IPC Writer → Rust Normalizer for full E2E visibility",
	)
}

func firstOrEmpty(ss []string) string {
	if len(ss) == 0 {
		return ""
	}
	return ss[0]
}

func lastOrEmpty(ss []string) string {
	if len(ss) == 0 {
		return ""
	}
	return ss[len(ss)-1]
}
