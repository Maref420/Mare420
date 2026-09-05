# ADR-006: WebSocket Market Data Ingestion Architecture

## Status
Accepted

## Context
Phase 1 (Market Data) requires real-time market data ingestion via WebSocket.
Current codebase has NO WebSocket implementation in any layer.
The websockets Python package exists in .venv but is unused and violates Matrix B.
Per governance, network/transfer ownership belongs to Go, not Python or Rust.
No ADR currently documents this architectural boundary.

## Decision
1. Create services/ingestion/ as a new Go module responsible exclusively for:
   - WebSocket connection establishment and lifecycle management
   - Reconnection with exponential backoff and circuit breaker
   - Heartbeat/ping-pong handling
   - Raw frame reception with receive timestamp and sequence tagging
   - Forwarding raw frames to Rust normalization layer via IPC

2. IPC Mechanism: Unix Domain Socket + Length-Prefixed Binary Protocol
   - Frame format: [4-byte big-endian length][raw payload]
   - Backpressure: Go buffers up to 1000 frames; if full, emits ws_ipc_backpressure metric
     and drops oldest frame with explicit log (NEVER silently blocks)

3. Configuration injected via environment variables only:
   - WS_URI, WS_AUTH_TOKEN, WS_RECONNECT_MAX_RETRIES,
     WS_RECONNECT_BASE_DELAY_MS, WS_HEARTBEAT_INTERVAL_MS, WS_IPC_SOCKET_PATH

4. Remove websockets from Python dependencies in next cleanup cycle.

## Consequences
- New Go module services/ingestion/ must be registered in Makefile
- Rust core_engine/market_data must implement Unix socket listener matching binary protocol
- Contract between Go and Rust is the IPC binary format, NOT tick-data-v1.json directly
- tick-data-v1.json remains the output contract of Rust normalization, unchanged
- All connection errors are explicitly logged and metriced; zero silent failures
- No Python module may ever open a WebSocket connection for market data

## Alternatives Considered
| Alternative | Reason Rejected |
|-------------|-----------------|
| Python websockets library | Violates Matrix B; Python owns agents/ML, not network IO |
| Rust tungstenite for WS client | Violates Matrix B; Rust owns compute/validation, not connection mgmt |
| gRPC between Go and Rust | Overkill for same-host; adds protobuf dependency and serialization overhead |
| Shared memory / mmap | Complex lifecycle; unsafe across language boundaries without extra coordination |
| REST polling fallback | Not real-time; would require separate ADR and dual-path maintenance |

## References
- Matrix B Language Ownership Policy: governance/policies/language-matrix.md
- Contract Management Policy: governance/policies/contract-management.md
- Market Data Contract: contracts/schemas/tick-data-v1.json
- P0 Phase 1 Definition: Governance Record CR-MKT-DATA-P0-001
