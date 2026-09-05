# Risk Engine — Task Specification

## Identity

- Module: docs/task_specs/risk/
- Language: Python/Rust (TBD)
- Owner: risk_team
- Policy: TBD

## Responsibility

Evaluate risk BEFORE execution. Decide Approve/Warn/Block based on exposure limits,
position limits, kill switch, circuit breaker. NEVER produce orders.

## Input Contract

StrategySignalEventV1 contract JSON (original, immutable).

Required fields: signal.symbol, signal.direction, signal.confidence, source_agent, event_id

## Processing Rules

1. Exposure Check: current exposure + proposed <= max_exposure_limit
2. Position Limit: open positions count <= max_open_positions
3. Kill Switch: if active -> BLOCK all signals
4. Circuit Breaker: if tripped -> BLOCK until cooldown complete
5. Confidence Threshold: confidence < min_threshold -> WARN (not block)
6. Every assessment MUST reference original event_id

## Output / Side Effects

- Risk Decision: APPROVE | WARN | BLOCK -> Execution Engine
- Risk Assessment Event -> Go Broker -> Memory System
- Audit Record -> risk_assessment

## Failure Behavior

- Assessment Error: BLOCK (fail-safe: when uncertain, deny)
- Timeout (>100ms): BLOCK
- Missing data: BLOCK + audit log

## Forbidden Actions

- Produce orders or signals
- Modify input payload
- Allow execution when assessment failed
- Cache risk decisions beyond TTL
- Bypass kill switch under any circumstances

## Dependencies

- <- core_engine/strategy (Contract JSON)
- -> core_engine/execution (Decision)
- -> services/message_broker (Assessment Event)
- -> Audit Sink

## Acceptance Criteria

- Valid signal within limits -> APPROVE
- Exposure exceeded -> BLOCK + reason
- Kill switch active -> BLOCK all
- Assessment timeout -> BLOCK (fail-safe)
- Every decision has audit trail
- Latency < 50ms p99
