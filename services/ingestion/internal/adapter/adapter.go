// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// ADR: docs/decisions/007-market-data-lifecycle-policy.md (INGEST stage)
// ADR: docs/decisions/007a-trace-id-propagation-addendum.md
// DESIGN: Pluggable exchange adapter pattern per ADR-007 extensibility
// WARNING: Adapters MUST NOT normalize, validate, or transform data.
//          Raw frames forwarded AS-IS to core_engine/market_data (Rust).

package adapter

import "context"

// ExchangeAdapter defines the contract for all exchange WebSocket adapters.
type ExchangeAdapter interface {
	Name() string
	Connect(ctx context.Context) error
	Subscribe(ctx context.Context, symbols []string) error
	ReadFrame(ctx context.Context) (frame []byte, traceID string, err error)
	Ping(ctx context.Context) error
	Close() error
	IsConnected() bool
}

// Config holds common configuration for all exchange adapters.
type Config struct {
	APIKey       string
	APISecret    string
	Testnet      bool
	Symbols      []string
	MaxReconnect int
	BaseDelayMs  int
}
