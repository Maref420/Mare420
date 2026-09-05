# Audit Sink — Task Specification

## Identity

- Module: intelligence/agent_control_plane/audit/
- Language: Python
- Owner: intelligence_team
- Policy: governance/policies/python-policy.yaml

## Responsibility

Immutable persistence of all strategy-signal-related events to Supabase audit_events.
ONLY persistence, no processing or decision-making.

## Input Contract

AuditRecord (pydantic model). Requires adding STRATEGY_SIGNAL_RECEIVED and
STRATEGY_SIGNAL_EXECUTED to AuditEventType enum. Payload: original contract JSON (immutable).

## Processing Rules

1. Every received strategy signal -> one STRATEGY_SIGNAL_RECEIVED record
2. Every execution outcome -> one STRATEGY_SIGNAL_EXECUTED record
3. Every risk assessment -> one RISK_ASSESSMENT record (existing type)
4. contract_version = "1.0.0"
5. resource = "strategy_signal:{event_id}"
6. Write-once: never update or delete

## Output / Side Effects

- Supabase audit_events table insert
- No other output

## Failure Behavior

- DB Connection Error: retry 3x with exponential backoff
- Schema Validation Error: log to stderr + continue (never block pipeline)
- Duplicate event_id: skip silently (idempotent)

## Forbidden Actions

- Modify or delete existing records
- Business processing or validation
- Blocking caller (must be async/non-blocking)
- Logging payload secrets
- Adding fields outside AuditRecord schema

## Dependencies

- <- core_engine/strategy (raw JSON)
- <- core_engine/execution (outcome)
- <- risk/risk_engine (assessment)
- -> Supabase audit_events

## Acceptance Criteria

- Every strategy signal produces exactly one audit record
- Records are immutable (no UPDATE/DELETE)
- Failed writes do not block pipeline
- AuditRecord passes pydantic validation
- Query by event_id returns complete trail
