# Risk Engine

> **Status:** spec_defined | **Owner:** risk_team | **Language:** Python/Rust (TBD)
> **Policy:** TBD | **Task Spec:** docs/task_specs/risk_engine.md

## Purpose

Evaluate risk BEFORE execution. Decide Approve/Warn/Block based on exposure limits,
position limits, kill switch, and circuit breaker state. This module NEVER produces
orders. It is a pure decision gate.

## Current State

This module currently contains ONLY specification documents. No executable code exists.

Existing documentation:
- risk/risk_engine/README.md (overview)
- risk/risk_engine/circuit_breaker/README.md
- risk/risk_engine/exposure_control/README.md
- risk/risk_engine/kill_switch/README.md
- risk/risk_engine/position_management/README.md
- risk/risk_engine/risk_assessment/README.md
- risk/risk_engine/validation/README.md

## Architecture (Target)

    StrategySignalEventV1 (Contract JSON)
            |
            v
    +---------------------+
    | Validation Layer    | <-- Schema + field checks
    +----------+----------+
               |
               v
    +---------------------+
    | Kill Switch Check   | <-- If active -> BLOCK immediately
    +----------+----------+
               |
               v
    +---------------------+
    | Circuit Breaker     | <-- If tripped -> BLOCK until cooldown
    +----------+----------+
               |
               v
    +---------------------+
    | Exposure Control    | <-- current + proposed <= limit
    +----------+----------+
               |
               v
    +---------------------+
    | Position Management | <-- open positions <= max
    +----------+----------+
               |
               v
    Decision: APPROVE | WARN | BLOCK
            |
            +--> Execution Engine (decision)
            +--> Audit Sink (assessment record)
            +--> Memory System (assessment event)

## Input Specification

StrategySignalEventV1 contract JSON (original, immutable).

Required fields: signal.symbol, signal.direction, signal.confidence, source_agent, event_id

## Processing Rules

1. Exposure Check: current exposure + proposed <= max_exposure_limit
2. Position Limit: open positions count <= max_open_positions
3. Kill Switch: if active -> BLOCK all signals (no exceptions)
4. Circuit Breaker: if tripped -> BLOCK until cooldown complete
5. Confidence Threshold: confidence < min_threshold -> WARN (not block)
6. Every assessment MUST reference original event_id
7. Assessment timeout (>100ms) -> BLOCK (fail-safe)

## Output Specification

| Output | Destination | Format |
|--------|-------------|--------|
| Risk Decision | Execution Engine | APPROVE / WARN / BLOCK enum |
| Assessment Event | Go Broker -> Memory | risk_assessment payload |
| Audit Record | Audit Sink | risk_assessment type |

## Failure Behavior

All failures default to BLOCK (fail-safe principle):
- Assessment error -> BLOCK
- Timeout -> BLOCK
- Missing data -> BLOCK + audit log

## Integration Guide (Future)

    # Python caller (example)
    from risk.risk_engine import assess_signal

    decision = assess_signal(contract_json)
    if decision == "APPROVE":
        execution_engine.execute(domain_event)
    elif decision == "WARN":
        log_warning(decision.reason)
        execution_engine.execute(domain_event)  # proceed with caution
    else:  # BLOCK
        audit_sink.record_rejection(decision.reason)

## Governance

| Artifact | Location |
|----------|----------|
| Task Spec | docs/task_specs/risk_engine.md |
| Sub-specs | risk/risk_engine/*/README.md |
| Policy | TBD |

### Forbidden Actions

- Produce orders or signals
- Modify input payload
- Allow execution when assessment failed
- Cache decisions beyond TTL
- Bypass kill switch under ANY circumstances

## Known Gaps

| Gap | Impact | Priority |
|-----|--------|----------|
| No executable code exists | Risk gate non-functional | P0 |
| Language not decided (Python vs Rust) | Architecture uncertainty | P0 |
| No policy file assigned | Governance incomplete | P0 |
| Not registered in module-ownership.yaml | Ownership unclear | P1 |
| No tests exist | Cannot verify behavior | P1 |
