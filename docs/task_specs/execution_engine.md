# Execution Engine — Task Specification

## Identity

- Module: core_engine/execution/
- Language: Rust
- Owner: core_engine_team
- Policy: governance/policies/rust-policy.yaml

## Responsibility

Receive DomainEvent from Strategy Engine, convert to Order Intent, send to Exchange Gateway.
ONLY execute orders that are valid and approved by Risk Engine.

## Input Contract

atlas_strategy_engine::DomainEvent (Rust struct) via internal function call (not JSON).

Required fields: signal_type, symbol, confidence_bps, side
Optional fields: quantity_scaled, price_scaled, stop_loss_scaled, take_profit_scaled

## Processing Rules

1. Only EntryLong/EntryShort produce orders. NoSignal is ignored.
2. confidence_bps must be >= configurable minimum threshold.
3. If quantity_scaled is None, use default position sizing.
4. Every order MUST preserve original event_id for traceability.
5. Before sending to gateway, Risk Approval MUST be received.

## Output / Side Effects

- Order Intent -> gateway.rs -> Exchange API
- Execution Outcome Event -> Memory System (via memory_events.rs)
- Audit Record -> strategy_signal_executed

## Failure Behavior

- Invalid DomainEvent: log + discard (never panic)
- Risk Rejected: log reason + discard
- Gateway Error: retry with backoff (max 3 attempts)
- Circuit Breaker Tripped: halt all execution immediately

## Forbidden Actions

- Produce order without Risk Approval
- Modify signal parameters after receipt
- Direct exchange call without going through gateway
- Ignore circuit breaker state
- Log sensitive data (API keys, account info)

## Dependencies

- <- core_engine/strategy (DomainEvent)
- <- docs/task_specs/risk (Approval)
- -> services/message_broker (Execution Outcome)
- -> intelligence/memory_system (Experience)

## Acceptance Criteria

- Valid LONG signal + Risk Approved -> Order created with correct side/quantity
- FLAT signal -> No order, no error
- Risk Rejected -> No order, audit logged
- Circuit Breaker tripped -> All execution halted
- 100% of orders traceable to original event_id
