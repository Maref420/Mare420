# ADR-007 Addendum: Data Lifecycle Trace ID Propagation

## Status
Accepted

## Context
CR-P0-004 Section H identified that the original ADR-007 lifecycle policy
lacked a concrete traceability mechanism. Without end-to-end trace IDs,
compliance audits cannot correlate trading decisions to source market data.
This addendum specifies the trace_id propagation contract across all
lifecycle stages without modifying the core lifecycle stage definitions.

## Decision

### 1. Trace ID Generation (INGEST Stage Only)
- Generated ONCE by Go adapter at ReadFrame() time
- Format: `{exchange}-{timestamp_ms}-{sequence}`
  - exchange: lowercase adapter name (e.g., "bybit", "okx")
  - timestamp_ms: uint64 milliseconds since Unix epoch
  - sequence: uint64 monotonic counter per adapter instance
- Example: `bybit-1725148800000-42`
- MUST be unique within a single deployment
- MUST be sortable by timestamp component

### 2. Propagation Contract
Every lifecycle stage MUST:
1. Receive trace_id from upstream (via IPC header or struct field)
2. Include trace_id in ALL emitted metrics as label
3. Include trace_id in ALL structured log entries
4. Forward trace_id unchanged to downstream stage
5. NEVER modify, truncate, or regenerate trace_id

| Stage | Receives From | Forwards To | Storage |
|-------|--------------|-------------|---------|
| INGEST | Self-generated | VALIDATE (IPC header) | N/A |
| VALIDATE | IPC header | NORMALIZE (NormalizedTick.trace_id) | Quarantine log |
| NORMALIZE | NormalizedTick | DISTRIBUTE (DistributionEvent.trace_id) | N/A |
| DISTRIBUTE | DistributionEvent | CONSUME, STORE, ARCHIVE | N/A |
| CONSUME | DistributionEvent | Agent decision log | Decision audit |
| STORE | DistributionEvent | Parquet metadata column | Queryable |
| ARCHIVE | DistributionEvent | Catalog metadata | Retrievable |
| PURGE | Any stage | Audit trail | Mandatory |

### 3. IPC Binary Format (Amendment to v1.1)
See contracts/schemas/ipc-binary-v1.spec.yaml trace_header section.
- Backward-compatible: legacy frames (flags=0x00) still parseable
- New frames: flags=0x01 followed by timestamp + exchange tag
- Rust parser MUST handle both formats

### 4. Sampling Strategy
- Default: 100% trace_id propagation (all frames carry trace_id)
- High-throughput mode (>10K fps): 1% full trace logging, 100% ID propagation
- Sampling decision made at INGEST only; downstream never samples
- Sampled-out frames still carry trace_id; only verbose logging is reduced

### 5. Compliance Query Interface
Given a trace_id, system MUST return:
- Source exchange + timestamp + symbol
- Validation result (pass/quarantine/reject)
- Normalized tick data
- Distribution timestamp + consumer acknowledgment
- Storage location (Parquet file + row offset)
- Archive status (if applicable)
- Purge record (if purged)

Implementation: Structured log aggregation + Parquet metadata index.
Full implementation deferred to P5 (Cold Archiver phase).

## Consequences
- IPC spec amended (backward-compatible, no breaking change)
- All adapters must generate trace_id (added to ExchangeAdapter interface)
- Rust NormalizedTick gains trace_id field
- All lifecycle_ metrics gain trace_id label (cardinality managed via sampling)
- Compliance-ready from Day 1 of production operation

## Compatibility
- Backward-compatible with ipc-binary-v1 legacy frames
- Forward-compatible: future adapters inherit trace generation
- No changes to lifecycle stage ordering or definitions

## Related
- ADR-007: Market Data Lifecycle Policy (parent)
- ADR-006: WebSocket Ingestion Architecture
- CR-P0-004: Lessons Learned (Section H trigger)
- ipc-binary-v1.spec.yaml: trace_header amendment
