# Governance Record

## Change ID
CR-MKT-DATA-P0-003

## Title
Market Data Lifecycle Policy (Extensible Framework)

## Status
Proposed (Pending ADR-007 Acceptance)

## Summary
Defined formal data lifecycle covering birth, ingest, validate, normalize,
distribute, consume, store, archive, and purge. Designed as extensible
framework with pluggable traits/interfaces at every stage. New sources,
validators, storage backends, importance criteria, and consumers can be
added without architectural rework via trait implementation + config change.

## Governance Alignment
- No governance rules changed
- Extends ADR-006 (IPC spec unchanged)
- Extension point mechanism prevents parallel paths
- All purge operations auditable and observable per Zero Silent Failures policy
- Config versioning enforces controlled evolution

## Affected Modules
- services/ingestion (source adapter interface)
- core_engine/market_data (validator + normalizer interfaces)
- core_engine/lifecycle (NEW: trait definitions + policy engine)
- core_engine/storage (storage backend interface)
- services/archiver (archive backend interface)
- intelligence/* (consumer protocol)

## Affected Contracts
- tick-data-v1.json (unchanged)
- ipc-binary-v1.spec.yaml (unchanged)
- NEW: lifecycle-config-v1.schema.yaml (to be created)
- NEW: NormalizedTick struct (Rust, to be defined)
- NEW: DistributionEvent struct (Rust, to be defined)

## Languages
- Rust: LifecycleStage, PluggableValidator, StorageBackend, ImportanceCriterion, PurgePolicy traits
- Go: MarketDataSource interface, archive backend
- Python: TickConsumer protocol

## Compatibility
- Backward-compatible: YES (extends ADR-006, no breaking changes)
- Forward-compatible: YES (extension points reserved)
- Breaking changes: Require new major ADR + config version bump

## Testing Evidence
- Trait interface tests: pending implementation
- Full lifecycle integration test: pending implementation
- Extension registration verification: pending implementation
- Purge audit test: pending implementation

## Rollback Plan
Remove docs/decisions/007-market-data-lifecycle-policy.md and this record.
No code or infrastructure affected (policy document only).

## Related ADRs
- ADR-006: WebSocket Ingestion Architecture
- ADR-007: Market Data Lifecycle Policy (this record)
- CR-MKT-DATA-P0-001: Phase 1 Market Data Stabilization
- CR-MKT-DATA-P0-002: WebSocket Ingestion Scaffold
