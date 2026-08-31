# Module: core_engine/market_data

## Purpose
Validates raw market data frames received via IPC, normalizes them to the
canonical tick-data-v1 contract, and distributes validated events to downstream
consumers. This module is the single authority for market data integrity.

## Boundary
- OWNS: Schema validation, normalization, quarantine, IPC deserialization, distribution
- DOES NOT OWN: WebSocket connection, network IO, strategy logic, storage persistence
- MUST NOT: Accept raw WebSocket frames directly (only via IPC from services/ingestion)

## Governance Alignment
- Matrix B Compliance: Rust (Compute/Validation Layer)
- Contract Policy: Outputs ONLY tick-data-v1 compliant events
- Testing Policy: Schema validation tests + golden dataset replay required
- ADR Reference: docs/decisions/006-websocket-ingestion-architecture.md
- Lifecycle Policy: docs/decisions/007-market-data-lifecycle-policy.md

## Architecture
services/ingestion (Go)
        |
        | Unix Domain Socket (ipc-binary-v1)
        v
+---------------------------+
| core_engine/market_data   |  <- Rust: Validate + Normalize + Distribute
|                           |
|  [IPC Listener]           |
|       |                   |
|  [PluggableValidator]     |
|       |                   |
|  [Normalizer]             |
|       |                   |
|  [Distributor]            |
+---------------------------+
        |
        +---> Hot Path: Python agents (NormalizedTick)
        +---> Warm Path: Storage backend (Parquet)
        +---> Quarantine: Invalid frames (TTL-based purge)

## Inputs
| Field | Source | Format | Validation |
|-------|--------|--------|------------|
| Raw WS Frames | services/ingestion via UDS | ipc-binary-v1 length-prefixed | Header + length check |
| Tick Schema | contracts/schemas/tick-data-v1.json | JSON Schema | Loaded at startup |

## Outputs
| Output | Consumer | Format | Guarantee |
|--------|----------|--------|-----------|
| NormalizedTick | Python agents, storage, archiver | Rust struct / serialized | Schema-valid only |
| QuarantinedFrame | Purge engine | Structured error + reason | TTL-based auto-purge |
| Validation Metrics | Observability | Prometheus counters/gauges | Real-time |

## Data Flow
1. Receive length-prefixed frame from UDS (ipc-binary-v1 spec)
2. Deserialize header: validate length bounds (1..16MB)
3. Run PluggableValidator chain against tick-data-v1 schema
4. If valid: normalize to NormalizedTick struct, emit to distributor
5. If invalid: create QuarantinedFrame with explicit reason, emit metric, buffer
6. Quarantine buffer: FIFO, max 100 entries, TTL 60min, auto-purge with audit log
7. NEVER silently drop, NEVER use default values, NEVER partially normalize

## Versioning
- Input contract: ipc-binary-v1.spec.yaml (shared with Go)
- Output contract: tick-data-v1.json (versioned, backward-compatible only)
- NormalizedTick struct: versioned with serde, breaking change requires new ADR

## Sharing / Consumption Model
### How Other Modules Consume This Module
- NEVER import Rust internals directly from Go or Python
- Hot path consumers subscribe to distribution channel (read-only NormalizedTick)
- Storage backends receive batches via StorageBackend trait
- Archive service receives tagged events via catalog metadata
- All consumption is PULL-based or event-driven, NEVER polling raw buffers

### Anti-Patterns (Forbidden)
- Direct memory sharing without serialization boundary
- Modifying NormalizedTick after emission
- Bypassing validator chain for "trusted" sources
- Silent quarantine overflow

## Error Handling
| Error Type | Behavior | Silenced? |
|------------|----------|-----------|
| IPC header malformed | Log hex dump + close connection + metric | NO |
| Schema validation fail | Quarantine + reason + metric | NO |
| Normalization panic | Catch, quarantine original frame, alert CRITICAL | NO |
| Distributor backpressure | Buffer bounded + drop oldest + metric | NO |
| Quarantine TTL expired | Auto-purge + audit log + metric | NO |

ZERO TOLERANCE: Every invalid frame produces observable evidence. No silent paths.

## Observability
- lifecycle_events_total{stage="validate", status}: counter
- lifecycle_events_total{stage="normalize", status}: counter
- lifecycle_latency_seconds{stage}: histogram
- lifecycle_quarantine_depth{reason}: gauge
- lifecycle_purge_total{stage="quarantine", reason, policy}: counter
- market_data_schema_errors_total{field}: counter
- market_data_normalized_ticks_total{symbol, venue}: counter

## Testing
| Test Type | Scope | Required? |
|-----------|-------|-----------|
| Unit | Validator chain, normalizer, quarantine logic | YES |
| Contract | IPC deserialization vs ipc-binary-v1.spec.yaml | YES |
| Schema | tick-data-v1.json validation (valid + invalid samples) | YES |
| Golden Dataset | Replay recorded frames through full pipeline | YES |
| Cross-Language | Go serialize -> Rust deserialize round-trip | YES |
| Failure Mode | Malformed IPC, schema violation, distributor saturated | YES |
| Purge Audit | Verify every quarantine purge produces metric + log | YES |

## Change Log
| Date | ADR | Change | Author |
|------|-----|--------|--------|
| 2026-09-01 | ADR-007 | Lifecycle stages VALIDATE + NORMALIZE defined, PluggableValidator interface specified | Atlas-AI Governance |
