
# ADR-001: Execution Contract Version Resolution
## Status: APPROVED
## Date: 2026-08-30
## Decided By: Project Architect
## Decision: Option 2 — Two Distinct Layers
- Layer 1 (Python): Agent Task Execution v0.1 — orchestration scope
- Layer 2 (Rust): Exchange Order Execution v1.0 — trading scope
- Boundary: Agent Runtime produces trade intents, Execution Engine fulfills them
## Compliance: No parallel paths, no module ownership violation

---

# ADR-002: Cross-Language Memory Experience Event Pipeline

## Status: APPROVED

## Date: 2026-08-30

## Decided By: Project Architect

## Context

Memory System had complete CRUD infrastructure but no operational data
ingestion path from production systems. ExperienceEngine was empty.
No cross-language flow existed for memory events.

## Decision

Add a Cross-Language Memory Event Pipeline:
Rust Core → Go Broker → Python ExperienceEngine → Supabase

Key design decisions:
1. Go Broker as mandatory intermediary (complies with Dependency Rules)
2. Shared contract schema as single source of truth
3. Triple-layer validation (Rust + Go + Python)
4. HTTP polling transport initially, NATS as approved future upgrade
5. Fire-and-forget from Rust (never blocks order processing)

## Files Created/Modified

New:
- contracts/schemas/memory/memory-experience-event-v1.json
- core_engine/execution/src/memory_events.rs
- intelligence/memory_system/experience_engine/engine.py
- intelligence/memory_system/experience_engine/subscriber.py
- services/message_broker/cmd/validate/main.go
- tests/production/test_cross_language_memory_pipeline.py
- tests/memory_system/test_experience_engine_production.py

Modified:
- core_engine/execution/src/lib.rs
- core_engine/execution/src/gateway.rs
- services/message_broker/internal/envelope/envelope.go

## Compliance

- No parallel paths created
- No module ownership violation
- Dependency Rules respected (Rust→Infrastructure→Python)
- Architecture Review ARCH-REVIEW-002 completed
- 28 production tests passing across all three languages

## ADR-2026-08-30-001: Market Data Uses Scaled Integers, Not Floats
- **Date**: 2026-08-30
- **Status**: Approved
- **Context**: Original SCHEMA_REQUEST.md specified float types for price/volume. This violates rust-policy.yaml deterministic_processing_required and introduces floating-point errors in financial calculations.
- **Decision**: All market data numeric fields SHALL use scaled integers (e.g., price_scaled, volume_scaled). Scale factors are defined per-exchange in configs/exchanges/.
- **Consequences**:
  - ✅ Deterministic arithmetic across Rust/Python/Go boundaries
  - ✅ Compliance with rust-policy.yaml
  - ⚠️ Requires scale_factor configuration for each exchange
  - ⚠️ FFI boundary must handle int↔decimal conversion explicitly
- **Contract**: contracts/schemas/market/tick-data-v1.json

## ADR-2026-08-30-002: Cross-Language Boundary Uses Serialization, Not Raw FFI
- **Date**: 2026-08-30
- **Status**: Approved
- **Context**: Audit revealed no #[no_mangle] exports or ctypes imports. System uses JSON serialization for all cross-language communication.
- **Decision**: 
  1. Renamed conceptual model from "FFI" to "Cross-Language Boundary" (contract name preserved for backward compat)
  2. Added MarketDataFeed interface to ffi-boundary-v1.json v1.1
  3. Added parity test for TickDataV1
  4. All numeric cross-boundary fields MUST use scaled integers
- **Consequences**:
  - ✅ Clear transport mechanism documented
  - ✅ Market Data now governed at boundary
  - ⚠️ Future raw FFI (e.g., PyO3) requires separate contract version
- **Contracts Updated**: ffi-boundary-v1.json (v1.1), tick-data-v1.json (v1)
- **Tests Added**: test_tick_data_v1_cross_language_parity

## ADR-2026-08-30-003: Production Artifact Cleanup & Secret Rotation
- **Date**: 2026-08-30
- **Status**: Executed
- **Context**: Audit revealed hardcoded password, misplaced .env, ad-hoc scripts, and local DB in production path.
- **Actions Taken (Additive/Safe)**:
  1. Hardcoded PASSWORD in setup_and_run.py → replaced with env-var (original backed up)
  2. .env migrated to configs/secure_api.env (original renamed, not deleted)
  3. Non-prod artifacts (.sh, test_*.py, users.db) → quarantined in output/_quarantine_/
  4. New production entrypoint created: output/secure_api/start.sh
- **Integrity Preserved**: All originals recoverable via .bak/.migrated/_quarantine
- **Next Steps**: 
  - Migrate users.db to Supabase/managed DB
  - Rotate SETUP_TEST_PASSWORD in production secrets manager
  - Remove quarantine after 7-day validation period

## ADR-2026-08-30-004: Execution/Risk Contracts Migrated to Scaled Integers
- **Date**: 2026-08-30
- **Status**: Executed
- **Context**: Audit revealed float types in order-v1, circuit-breaker-v1, risk-assessment-v1. Violates rust-policy.yaml deterministic_processing_required.
- **Decision**: All numeric financial fields migrated to scaled integers:
  - quantity/price/stop_price → integer (scaled per exchange config)
  - max_daily_loss_pct → integer in basis points (1bp = 0.01%)
  - risk_score → integer 0-10000 (maps to 0.0000-1.0000)
- **Integrity**: Original structures, rules, ownership preserved. Only field_types modified.
- **Contracts Updated**: order-v1.1, circuit-breaker-v1.1, risk-assessment-v1.1
- **Backups**: *.bak.pre-deterministic.*

## ADR-2026-08-30-005: Market Data Rust Skeleton Created
- **Date**: 2026-08-30
- **Status**: Executed
- **Context**: tick-data-v1.json existed but had no Rust implementation. Contract without code = dead contract.
- **Decision**: Created minimal skeleton at core_engine/market_data/:
  - Cargo.toml with governance-compliant lints (no unsafe, no unwrap, deny clippy)
  - types.rs with TickDataV1 struct matching tick-data-v1.json exactly
  - Validation method with explicit error types (no panics)
  - Unit tests for validation + serialization roundtrip
  - lib.rs as module root
- **Integrity**: All files are new additions. No existing code modified.
- **Next Steps**: Implement ingestion pipeline, connect to Go exchange adapters, add boundary tests

## ADR-2026-08-30-006: Scoped clippy::panic Allow in Test Modules Only
- **Date**: 2026-08-30
- **Status**: Executed
- **Context**: rust-policy.yaml denies panic, unwrap, and expect globally. However, Rust unit tests inherently require assertion macros that expand to panic. Applying the deny lint to test code makes testing impossible without violating policy.
- **Decision**: Use `#[cfg_attr(test, allow(clippy::panic))]` scoped exclusively to `#[cfg(test)] mod tests`. Production code remains strictly panic-free. This is the standard Rust ecosystem pattern for strict no-panic policies, not a workaround.
- **Constraints**:
  - ONLY applies within `#[cfg(test)]` blocks
  - ONLY allows `clippy::panic` (unwrap/expect remain denied everywhere)
  - MUST include governance comment referencing this ADR
  - Production code validated separately via pre-test scan
- **Integrity**: No policy files modified. No parallel paths created.
- **Files Affected**: core_engine/market_data/src/types.rs (test module only)
- **Validation**: cargo check ✅ | cargo test ✅ | cargo clippy --all-targets ✅
