# Module: services/ingestion

## Purpose
Receives raw market data via WebSocket, manages connection lifecycle, and forwards
unprocessed frames to the Rust normalization layer via Unix Domain Socket IPC.
This module owns NO business logic, validation, or transformation.

## Boundary
- OWNS: WebSocket connection, reconnection, heartbeat, raw frame buffering, IPC forwarding
- DOES NOT OWN: Parsing, validation, normalization, strategy logic, storage
- MUST NOT: Modify, filter, enrich, or interpret market data content

## Governance Alignment
- Matrix B Compliance: Go (Network/Transfer Layer)
- Contract Policy: Outputs ONLY raw frames via IPC; normalized output owned by core_engine/market_data
- Testing Policy: Connection resilience tests required; no silent failures allowed
- ADR Reference: docs/decisions/006-websocket-ingestion-architecture.md

## Architecture
External WS Source
        |
        v
+---------------------+
| services/ingestion  |  <- Go: WebSocket Client + IPC Sender
+----------+----------+
           | Unix Domain Socket (length-prefixed binary)
           v
+-------------------------+
| core_engine/market_data |  <- Rust: Validation + Normalization
+-------------------------+

## Inputs
| Field | Source | Description |
|-------|--------|-------------|
| WS_URI | env | WebSocket endpoint (wss://...) |
| WS_AUTH_TOKEN | env | API key/token (never hardcoded) |
| WS_RECONNECT_MAX_RETRIES | env | Max reconnection attempts before circuit break |
| WS_RECONNECT_BASE_DELAY_MS | env | Base delay for exponential backoff |
| WS_HEARTBEAT_INTERVAL_MS | env | Ping interval for keepalive |
| WS_IPC_SOCKET_PATH | env | Unix socket path for Go->Rust IPC |

## Outputs
| Output | Consumer | Format | Guarantee |
|--------|----------|--------|-----------|
| Raw WS Frames | core_engine/market_data | [4B BE length][payload] via UDS | At-least-once with backpressure drop |
| Connection Metrics | Observability Stack | Prometheus/OpenTelemetry | Real-time |
| Error Events | Alert System / Logs | Structured error with context | Never silenced |

## Data Flow
1. Go establishes WebSocket connection using WS_URI and WS_AUTH_TOKEN
2. Raw frames received -> tagged with monotonic sequence + receive timestamp (ns)
3. Frames serialized as [4-byte big-endian length][raw payload] and written to UDS
4. If UDS write buffer full (>1000 frames): emit ws_ipc_backpressure, drop oldest, log reason
5. Connection errors -> explicit error event emitted (NEVER silently retried beyond policy)
6. Reconnection follows exponential backoff; each attempt logged with reason and attempt count

## Versioning
- This module produces NO versioned data contract
- Consumes external WS protocol (documented externally by exchange/vendor)
- IPC binary format versioned independently; current version: v1 (implicit in ADR-006)
- tick-data-v1.json is output of Rust layer, NOT this module

## Sharing / Consumption Model
### How Other Modules Consume This Module
- NEVER import Go code directly into Rust/Python
- NEVER consume raw WS frames outside this module
- ONLY core_engine/market_data receives output via Unix Domain Socket IPC
- Observability consumers read metrics/logs via standard interfaces
- Configuration injected via environment variables only (no hardcoded values)

### Anti-Patterns (Forbidden)
- Direct socket access from Python agents
- Parsing WS frames in Go before forwarding
- Silent reconnection without logging
- Fallback to REST/polling without separate ADR
- Blocking indefinitely on IPC write (must use timeout + backpressure)

## Error Handling
| Error Type | Behavior | Silenced? |
|------------|----------|-----------|
| Connection refused | Log + emit error event + retry per backoff policy | NO |
| Auth failure (401/403) | Log + emit CRITICAL alert + stop (no retry) | NO |
| Frame corruption detected | Forward as-is + attach corruption flag in metadata | NO |
| IPC socket unavailable | Buffer up to 1000 frames + emit backpressure metric | NO |
| IPC buffer overflow | Drop oldest frame + log dropped sequence + emit metric | NO |
| Heartbeat timeout | Close connection + emit timeout error + trigger reconnect | NO |
| Unexpected close code | Log code + reason + emit error event + trigger reconnect | NO |

ZERO TOLERANCE: No error may be caught and discarded. Every failure must produce observable evidence.

## Observability
- ws_connection_state: gauge (connected/disconnected/reconnecting/circuit_broken)
- ws_frames_received_total: counter
- ws_frames_forwarded_total: counter
- ws_frames_dropped_total: counter (with reason label: backpressure/auth/timeout)
- ws_reconnection_attempts_total: counter (with reason label)
- ws_ipc_backpressure: gauge (current buffered frame count)
- ws_heartbeat_failures_total: counter
- ws_error_events_total: counter (with error_type label)

## Testing
| Test Type | Scope | Required? |
|-----------|-------|-----------|
| Unit | Frame serialization, sequence numbering, backpressure logic | YES |
| Contract | IPC binary format matches Rust consumer expectation | YES |
| Integration | Mock WS server + full Go->UDS->Rust pipeline | YES |
| Failure Mode | Connection drop, auth expiry, IPC breakdown, heartbeat timeout | YES |
| Backpressure | IPC saturated -> buffer fill -> drop oldest verified | YES |
| Golden Dataset | Recorded raw WS frames replayed through full pipeline | YES |
| Config Validation | Missing/invalid env vars -> explicit startup failure | YES |

## Change Log
| Date | ADR | Change | Author |
|------|-----|--------|--------|
| 2026-09-01 | ADR-006 | Initial module creation per P0 Market Data | Atlas-AI Governance |
| 2026-09-01 | CR-MKT-DATA-P0-002 | Scaffold complete, governance registered, tests skeletonized | Atlas-AI Governance |
| 2026-09-01 | ADR-007 | Lifecycle stage INGEST defined, MarketDataSource interface specified | Atlas-AI Governance |
