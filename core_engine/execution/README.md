# Execution Engine

> **Status:** wired_pending | **Owner:** core_engine_team | **Language:** Rust
> **Crate:** atlas-execution-engine v0.1.0 | **Policy:** governance/policies/rust-policy.yaml

## Purpose

Convert validated strategy signals into executable orders and dispatch them to the
exchange gateway. This module is the ONLY path through which orders leave the system.
No order may be created outside this module.

## Architecture

    DomainEvent (from Strategy Engine)
            |
            v
    +---------------------+
    | validator.rs        | <-- Validate domain fields + business rules
    +----------+----------+
               |
               v
    +---------------------+
    | order_manager.rs    | <-- Convert signal -> Order Intent
    +----------+----------+     Apply position sizing
               |                Preserve event_id traceability
               v
    +---------------------+
    | gateway.rs          | <-- Send to Exchange API
    +----------+----------+     Retry with backoff
               |                Respect circuit breaker
               v
    +---------------------+
    | memory_events.rs    | <-- Emit Execution Outcome Event
    +---------------------+     -> Memory System

    Risk Gate: atlas_risk_engine::envelope (imported at lib.rs level)
    All orders MUST pass risk check before gateway dispatch.

## Input Specification

### Source

atlas_strategy_engine::DomainEvent via internal Rust function call.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| signal_type | SignalType | EntryLong, EntryShort, ExitLong, ExitShort, NoSignal |
| symbol | String | Trading pair (e.g., BTCUSDT) |
| confidence_bps | u32 | Evidence strength in basis points (0-10000) |
| side | Option<String> | "buy" or "sell" (required for entry/exit signals) |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| quantity_scaled | Option<u64> | Position size in scaled units |
| price_scaled | Option<u64> | Target price in scaled units |
| stop_loss_scaled | Option<u64> | Stop loss in scaled units |
| take_profit_scaled | Option<u64> | Take profit in scaled units |
| event_id | Uuid | Original signal event ID (preserved for traceability) |
| agent_id | String | Source agent identifier |

## Processing Pipeline

1. Receive DomainEvent from Strategy Engine
2. Validate domain constraints (validator.rs)
3. Check risk approval via atlas_risk_engine::envelope
4. If approved: convert to Order Intent (order_manager.rs)
5. Dispatch to exchange (gateway.rs)
6. Emit execution outcome (memory_events.rs)
7. If rejected at any stage: log reason + discard (never panic)

## Output Specification

| Output | Destination | Format | When |
|--------|-------------|--------|------|
| Order Intent | gateway.rs -> Exchange API | Internal struct | Post risk approval |
| Execution Outcome | Memory System via broker | memory-experience-event-v1 JSON | Post execution |
| Audit Record | Audit Sink | audit-storage-v1 JSON | Every signal received |
| Metrics | foundation/metrics | Counter/Histogram | Every stage transition |

## Integration Guide

### Receiving Signals from Strategy Engine

    use atlas_strategy_engine::DomainEvent;
    use atlas_execution_engine::order_manager;

    fn handle_signal(event: DomainEvent) {
        match event.signal_type {
            SignalType::EntryLong | SignalType::EntryShort => {
                // Validate -> Risk Check -> Create Order -> Dispatch
            }
            SignalType::NoSignal => { /* skip */ }
            _ => { /* exit/adjust logic */ }
        }
    }

### Emitting Execution Outcomes

    use atlas_execution_engine::memory_events;

    memory_events::emit_outcome(
        event_id,      // original signal event_id
        order_id,
        symbol,
        side,
        quantity_scaled,
        pnl_scaled,
        status,        // filled | rejected | cancelled | halted_by_circuit_breaker
    );

## Testing

    cd core_engine/execution
    cargo test                    # Unit tests
    cargo clippy -- -D warnings   # Lint check

Existing test files:
- tests/order_tests.rs
- tests/prod_circuit_breaker_gate.rs
- tests/prod_memory_pipeline.rs

## Governance

| Artifact | Location |
|----------|----------|
| Crate | core_engine/execution/Cargo.toml |
| Policy | governance/policies/rust-policy.yaml |
| Risk Dependency | atlas_risk_engine::envelope |
| Memory Contract | contracts/schemas/memory/memory-experience-event-v1.json |
| Audit Contract | contracts/schemas/audit/audit-storage-v1.json |

### Approved Dependencies

serde (derive), uuid (v4, serde), chrono (serde)

### Forbidden Actions

- Produce order without risk approval
- Modify signal parameters after receipt
- Direct exchange call bypassing gateway.rs
- Ignore circuit breaker state
- Log sensitive data (API keys, account info)
- Panic on invalid input (always return Result)

## Known Gaps

| Gap | Impact | Priority |
|-----|--------|----------|
| Strategy Engine DomainEvent not wired to validator.rs | Signals not consumed | P0 |
| Risk gate integration untested end-to-end | Orders may bypass risk | P0 |
| Execution outcome not connected to Memory subscriber | Learning loop broken | P1 |
| Audit sink not called on signal receipt | Missing compliance trail | P1 |
