// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// CONTRACT: IPC binary format v1 (length-prefixed over UDS)
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml

package main

import (
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/atlas-ai/services/ingestion/internal/metrics"
)

func main() {
	// Register all Prometheus metrics BEFORE any other operation.
	// This ensures observability is available even in scaffold mode.
	metrics.Register()

	if os.Getenv("ATLAS_SCAFFOLD_MODE") == "1" {
		slog.Warn("atlas-ws-ingestion: running in SCAFFOLD MODE - no WS connection will be established")
		slog.Info("metrics registered and available at /metrics endpoint")
		slog.Info("set ATLAS_SCAFFOLD_MODE=0 and implement business logic to enable real operation")

		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh

		slog.Info("atlas-ws-ingestion: scaffold mode shutting down gracefully")
		os.Exit(0)
	}

	slog.Error("atlas-ws-ingestion: business logic not yet implemented")
	slog.Error("this binary MUST NOT run in production without completed implementation per ADR-006")
	os.Exit(1)
}
