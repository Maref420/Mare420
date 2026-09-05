# ADR-007: Market Data Lifecycle Policy (Extensible Framework)

## Status
Accepted

## Context
Phase 1 infrastructure is complete (ADR-006, IPC spec, cross-validation).
The system now requires a formal data lifecycle definition covering birth,
validation, distribution, consumption, storage, archival, and purge.
This policy must be extensible to accommodate future requirements without
architectural rework: new storage backends, regulatory changes, additional
consumer types, and evolving importance classification criteria.

## Decision

### 1. Lifecycle Stages (Ordered Pipeline)
Data flows through exactly these stages in order. No stage may be skipped.
New stages may be INSERTED between existing stages via extension points.

BIRTH -> INGEST -> VALIDATE -> NORMALIZE -> [EXTENSION_POINT_1] ->
DISTRIBUTE -> [EXTENSION_POINT_2] -> CONSUME | STORE | ARCHIVE
                                                |
                                          PURGE (any stage)

| Stage | Owner | Contract | Extensible? |
|-------|-------|----------|-------------|
| BIRTH | External source | N/A | No (external) |
| INGEST | Go services/ingestion | ipc-binary-v1 | Yes (new sources via adapter) |
| VALIDATE | Rust core_engine/market_data | tick-data-v1.json | Yes (pluggable validators) |
| NORMALIZE | Rust core_engine/market_data | NormalizedTick | Yes (transform pipeline) |
| DISTRIBUTE | Rust core_engine/distributor | DistributionEvent | Yes (pluggable sinks) |
| CONSUME | Python intelligence/* | NormalizedTick (read-only) | Yes (new agent types) |
| STORE | Rust core_engine/storage | Parquet schema | Yes (pluggable backends) |
| ARCHIVE | Go/Rust services/archiver | Catalog metadata | Yes (pluggable targets) |
| PURGE | All stages | PurgeEvent (metric+log) | Yes (policy engine) |

### 2. Extension Point Mechanism
Each extension point is a trait/interface that new implementations register against.

Rust side:
- LifecycleStage trait: name(), process(), metrics()
- PluggableValidator trait: validate(), priority()
- StorageBackend trait: write(), retention_policy(), purge_expired()
- ImportanceCriterion trait: evaluate(), weight()
- PurgePolicy trait: should_purge(), purge_action(), audit_log()

Go side:
- MarketDataSource interface: Name(), Connect(), ReadFrame(), Health(), Close()

Python side:
- TickConsumer protocol: on_tick(), consumer_id(), backpressure_policy()

### 3. Importance Classification (Pluggable Criteria)
Chain-of-responsibility pattern. New criteria added without modifying existing code.

Built-in criteria (initial):
- RegulatoryRequirement (weight: 0, mandatory)
- IncidentCorrelation (weight: 10)
- StrategyPnLImpact (weight: 20)
- AnomalyDetection (weight: 30)
- ManualFlag (weight: 40)
- DefaultRetention (weight: 100, fallback)

Future criteria require only trait implementation + config registration.

### 4. Purge Policy Engine
All purge operations go through centralized policy engine. NEVER ad-hoc.
Every purge emits: metric + structured log + audit trail for regulated data.

### 5. Configuration Schema (Versioned)
Lifecycle config is versioned YAML, validated at startup.
Changes require config version bump. Breaking changes require new major ADR.

### 6. Observability (Lifecycle-Aware Metrics)
All metrics prefixed with lifecycle_ for unified dashboarding:
- lifecycle_events_total{stage, status}
- lifecycle_latency_seconds{stage}
- lifecycle_purge_total{stage, reason, policy}
- lifecycle_quarantine_depth{reason}
- lifecycle_storage_bytes{backend, partition}
- lifecycle_archive_pending{retention_class}
- lifecycle_classification_total{criterion, tag}
- lifecycle_extension_loaded{stage, plugin_name}

## Consequences
- New sources/validators/backends/criteria/consumers: implement trait + config
- Config changes: bump version, validate at startup
- NO stage removal or reorder without new major ADR
- ALL purge operations auditable and observable

## Extensibility Guarantees
| Change Type | Code Change? | ADR? | Config Version? |
|-------------|-------------|------|-----------------|
| Add new WS source | No (trait) | No | Minor |
| Add new validator | No (trait) | No | Minor |
| Add storage backend | No (trait) | Amendment | Minor |
| Add importance criterion | No (trait) | No | Minor |
| Change stage ordering | YES | NEW Major | Major |
| Remove a stage | YES | NEW Major | Major |
| Change IPC format | YES | NEW Major | Major |
| Add lifecycle stage | YES (extension) | Amendment | Minor |
| Change purge policy | No (config) | No | Patch |

## Compatibility
- Backward-compatible with ADR-006 (IPC spec unchanged)
- Forward-compatible: extension points reserved for future use
- Config versioning prevents accidental breaking changes

## Testing Requirements
- Unit tests for each trait implementation
- Integration test: full lifecycle BIRTH->PURGE with golden dataset
- Extension registration test: verify all plugins loaded at startup
- Purge audit test: verify every purge produces metric + log
- Config validation test: reject invalid/malformed lifecycle config

## Related ADRs
- ADR-006: WebSocket Ingestion Architecture
- CR-MKT-DATA-P0-001: Phase 1 Market Data Stabilization
- CR-MKT-DATA-P0-002: WebSocket Ingestion Scaffold

## References
- IPC Spec: contracts/schemas/ipc-binary-v1.spec.yaml
- Tick Schema: contracts/schemas/tick-data-v1.json
- Governance Policies: governance/policies/
