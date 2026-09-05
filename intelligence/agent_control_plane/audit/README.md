# Audit Sink

> **Status:** ready_for_wiring | **Owner:** intelligence_team | **Language:** Python
> **Contract:** contracts/schemas/audit/audit-storage-v1.json | **Policy:** governance/policies/python-policy.yaml

## Purpose

Immutable persistence of all auditable events to Supabase audit_events table.
This module provides write-only, append-only storage. No processing, no decisions,
no modifications.

## Architecture

    Event Source (any module)
            |
            v
    +---------------------+
    | AuditRecord         | <-- Pydantic validation
    | (models.py)         |     extra=forbid, frozen=True
    +----------+----------+
               |
               v
    +---------------------+
    | AuditSink Interface | <-- Abstract boundary
    | (interface.py)      |     record(event: AuditRecord)
    +----------+----------+
               |
               v
    +---------------------+
    | SupabaseAuditSink   | <-- Supabase client
    | (database_sink.py)  |     table("audit_events").insert()
    +---------------------+

## Input Specification

### AuditRecord (pydantic model)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| contract_version | str | Yes | e.g., "1.0.0" |
| event_id | str | Yes | Unique event identifier |
| event_type | AuditEventType | Yes | Enum (see below) |
| operation_id | str | Yes | Operation correlation ID |
| agent_id | str | Yes | Source agent |
| timestamp | datetime | Yes | Event time |
| action | AuditAction | Yes | requested / completed / failed |
| resource | str | Yes | e.g., "strategy_signal:{event_id}" |
| result | AuditResult | Yes | success / failure |
| metadata | dict[str, Any] | Yes | Extensible payload |

### Current AuditEventType Values

- MEMORY_RETRIEVE = "memory.retrieve"
- MEMORY_STORE = "memory.store"
- MEMORY_FORGET = "memory.forget"
- COMMUNICATION_SEND = "communication.send"
- SCHEDULER_TASK = "scheduler.task"

### MISSING Types (Required for Strategy Signals)

- STRATEGY_SIGNAL_RECEIVED = "strategy_signal.received"
- STRATEGY_SIGNAL_EXECUTED = "strategy_signal.executed"
- RISK_ASSESSMENT = "risk.assessment"

These MUST be added to AuditEventType enum before wiring.

## Integration Guide

### Recording a Strategy Signal Receipt

    from intelligence.agent_control_plane.audit.database_sink import SupabaseAuditSink
    from intelligence.agent_control_plane.audit.models import AuditRecord, AuditAction, AuditResult
    from datetime import datetime, timezone

    sink = SupabaseAuditSink()
    record = AuditRecord(
        contract_version="1.0.0",
        event_id=signal_event_id,
        event_type="strategy_signal.received",  # requires enum addition
        operation_id=operation_id,
        agent_id=source_agent,
        timestamp=datetime.now(timezone.utc),
        action=AuditAction.COMPLETED,
        resource=f"strategy_signal:{signal_event_id}",
        result=AuditResult.SUCCESS,
        metadata={"raw_payload": original_json},
    )
    sink.record(record)

## Failure Behavior

- DB Connection Error: retry 3x with exponential backoff
- Schema Validation Error: log to stderr + continue (never block pipeline)
- Duplicate event_id: skip silently (idempotent)

## Testing

    cd /root/Atlas-AI
    python -m pytest tests/contracts/test_audit_contract.py -v

## Governance

| Artifact | Location |
|----------|----------|
| Interface | intelligence/agent_control_plane/audit/interface.py |
| Models | intelligence/agent_control_plane/audit/models.py |
| Supabase Sink | intelligence/agent_control_plane/audit/database_sink.py |
| Memory Sink | intelligence/agent_control_plane/audit/memory_sink.py |
| Contract | contracts/schemas/audit/audit-storage-v1.json |

### Forbidden Actions

- Modify or delete existing records
- Business processing or validation
- Blocking caller (must be async/non-blocking)
- Logging payload secrets
- Adding fields outside AuditRecord schema

## Known Gaps

| Gap | Impact | Priority |
|-----|--------|----------|
| AuditEventType missing strategy_signal types | Cannot record strategy events | P1 |
| Not wired to Strategy Engine | No automatic audit trail | P1 |
| Not wired to Execution Engine | Execution outcomes not logged | P1 |
| Not wired to Risk Engine | Risk decisions not logged | P1 |
