# Market Strategy Event Module

> **Status:** parity_verified | **Owner:** core_engine_team | **Language:** Rust
> **Contract:** strategy-signal-event-v1 | **Policy:** governance/policies/rust-policy.yaml

## Purpose

Receive, validate, convert, and dispatch market strategy signals from the
Intelligence Layer (Python) to downstream consumers (Execution, Risk, Audit, Memory).

This module is the single entry point for all strategy signals entering
the Rust compute boundary. No strategy signal may bypass this module.

---

## Data Input Specification

### Contract Boundary

All input MUST conform to contracts/schemas/strategy/strategy-signal-event-v1.schema.json.

| Field | Type | Required | Constraint | Description |
|-------|------|----------|------------|-------------|
| version | string | Yes | const 1.0.0 | Schema version |
| event_id | UUID v4 | Yes | unique | Traceability identifier |
| timestamp_utc | string | Yes | ISO 8601 UTC | Event creation time |
| trace_id | UUID v4 | No | valid UUID | Distributed tracing |
| source_agent | string | Yes | non-empty | Producer agent name |
| signal.symbol | string | Yes | ^[A-Z0-9]{2,20}$ | Trading pair |
| signal.direction | enum | Yes | LONG/SHORT/FLAT | Position intent |
| signal.confidence | float | Yes | [0.0, 1.0] | Evidence strength |
| signal.regime | enum | Yes | TRENDING/RANGING/VOLATILE/CALM | Market context |
| signal.parameters | object | No | arbitrary | Strategy-specific params |
| metadata | object | No | map<string,string> | Extensible metadata |

### Canonical Serialization Format

Cross-language parity requires deterministic JSON:
- Sorted keys (alphabetical at all levels)
- Compact format (no whitespace)
- Optional fields omitted when absent
- Empty objects omitted

### Python Producer API

    from intelligence.strategy_intelligence.contract_adapter import StrategySignalEventV1

    event = StrategySignalEventV1.create(
        source_agent="momentum_v3",
        symbol="BTCUSDT",
        direction="LONG",
        confidence=0.87,
        regime="TRENDING",
    )
    json_bytes = event.to_json()

### Deserialization Entry Point (Rust)

    use atlas_strategy_engine::ContractEvent;
    let event: ContractEvent = serde_json::from_str(&json_input)?;
    event.validate_contract()?;

---

## Processing Pipeline

    JSON Input
        |
        v
    Stage 1: Contract Validation (contract_types.rs)
      - Schema enforcement
      - deny_unknown_fields
      - Pattern/range checks
        |
        v OK
    Stage 2: Domain Conversion (conversions.rs)
      - f64 [0,1] -> u32 bps
      - Direction -> SignalType
      - ISO 8601 -> nanos
      - source_agent -> agent_id
        |
        v OK
    Stage 3: Domain Validation (domain_types.rs)
      - Business rules
      - Scaled integer checks
      - Side required for entries
        |
        v OK
    Stage 4: Consumer Dispatch (TO BE WIRED)
      - Execution Engine
      - Risk Engine
      - Audit Sink
      - Memory System

### Error Handling (Fail-Fast)

Every stage rejects invalid data immediately. Errors NEVER propagate
to downstream stages.

| Stage | Error Type | Behavior |
|-------|-----------|----------|
| Deserialization | serde_json::Error | Reject, log, discard |
| Contract Validation | ContractValidationError | Reject, log, discard |
| Domain Conversion | ConversionError | Reject, log, discard |
| Domain Validation | StrategyValidationError | Reject, log, discard |

---

## Consumer Integration Guide

### For Execution Engine (core_engine/execution/)

    use atlas_strategy_engine::{DomainEvent, SignalType};

    fn process_signal(event: DomainEvent) {
        match event.signal_type {
            SignalType::EntryLong | SignalType::EntryShort => {
                // event.confidence_bps: u32 (0-10000)
                // event.side: Option<String>
                // event.quantity_scaled: Option<u64>
            }
            SignalType::NoSignal => {}
            _ => {}
        }
    }

Required fields: signal_type, symbol, confidence_bps, side
Optional fields: quantity_scaled, price_scaled, stop_loss_scaled, take_profit_scaled

### For Risk Engine (docs/task_specs/risk/)

Risk receives the SAME contract JSON (not domain types).
Re-validates independently before approving execution.

    from intelligence.strategy_intelligence.contract_adapter import StrategySignalEventV1
    event = StrategySignalEventV1.from_json(raw_json)

### For Audit Sink (intelligence/agent_control_plane/audit/)

    from intelligence.agent_control_plane.audit.database_sink import SupabaseAuditSink
    sink.persist(AuditRecord(
        event_type="strategy_signal_received",
        payload=raw_json,
        source="strategy_engine",
    ))

### For Memory System (intelligence/memory_system/)

Store AFTER execution outcome is known (not on receipt).
Links signal to outcome for learning.

---

## Output Specification

| Output | Consumer | Format | When |
|--------|----------|--------|------|
| Validated DomainEvent | Execution Engine | Rust struct | Post domain validation |
| Contract JSON (original) | Audit Sink | Immutable JSON | On receipt |
| Risk assessment request | Risk Engine | Contract JSON | Pre-execution |
| Experience record | Memory System | Event + outcome | Post-outcome |
| Metrics | foundation/metrics | Counter/Histogram | Every stage |

---

## Testing

    # Rust (17 tests)
    cd core_engine/strategy && cargo test

    # Python contract (7 tests)
    python -m pytest tests/contracts/test_strategy_signal_contract.py -v

    # Python adapter (11 tests)
    python -m pytest tests/contracts/test_strategy_signal_python_contract.py -v

    # Cross-language parity (10 tests)
    python -m pytest tests/production/test_cross_language_parity.py -v

Current Status: 51/51 PASSED

---

## Governance

| Artifact | Location |
|----------|----------|
| Schema | contracts/schemas/strategy/strategy-signal-event-v1.schema.json |
| Envelope | contracts/events/strategy/strategy-signal-envelope-v1.md |
| Ownership | governance/ownership/module-ownership.yaml |
| Policy | governance/policies/rust-policy.yaml |
| Registry | governance/registry/dependencies.yaml |
| Fixture | tests/fixtures/strategy/strategy-signal-event-v1-canonical.json |

Approved Dependencies: serde, serde_json, thiserror, uuid (all approved 2026-08-31)

---

## Known Gaps

| Gap | Impact | Priority | Owner |
|-----|--------|----------|-------|
| Execution Engine not wired | Signals have no effect | P0 | core_engine_team |
| Risk Engine not wired | No pre-execution gate | P0 | risk_team |
| Audit Sink not connected | No compliance trail | P1 | intelligence_team |
| Go Broker routing incomplete | No persistent transport | P1 | platform_team |
| Timestamp parser placeholder | Non-deterministic ns | P2 | core_engine_team |
