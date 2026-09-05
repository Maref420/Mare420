"""Experience Engine: Convert operational outcomes into Episodic Memory.

Governed by:
- contracts/schemas/memory/memory-experience-event-v1.json
- governance/policies/memory/lifecycle-policy.yaml
- Architecture Review: ARCH-REVIEW-002

Rules:
- NEVER writes directly to storage
- ALWAYS produces MemoryRecord(type=EPISODIC, status=VALIDATED)
- ALWAYS routes through MemoryKernel.store()
- ALWAYS includes operation_id + agent_id for traceability
- ALWAYS audits every capture attempt
- NEVER produces Semantic or Procedural memory
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from intelligence.agent_control_plane.audit.interface import AuditSink
from intelligence.agent_control_plane.audit.models import (
    AuditAction,
    AuditEventType,
    AuditRecord,
    AuditResult,
)
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)


class ExperienceEngine:
    """Convert raw operational outcomes into validated Episodic Memory."""

    def __init__(self, kernel: MemoryKernel, audit_sink: AuditSink) -> None:
        self._kernel = kernel
        self._audit = audit_sink

    def capture_execution_outcome(
        self,
        *,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        pnl: float,
        status: str,
        agent_id: str,
        operation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """Capture an execution outcome as Episodic Memory.

        Raises ValueError if required fields are invalid.
        Audits SUCCESS on store, FAILURE on any error.
        """
        if not order_id:
            raise ValueError("order_id must not be empty")
        if not symbol:
            raise ValueError("symbol must not be empty")
        if side not in ("buy", "sell"):
            raise ValueError(f"side must be buy or sell, got {side!r}")
        if status not in ("filled", "rejected", "cancelled", "halted_by_circuit_breaker"):
            raise ValueError(f"invalid status: {status!r}")

        record = MemoryRecord(
            memory_id=str(uuid.uuid4()),
            memory_type=MemoryType.EPISODIC,
            created_at=datetime.now(timezone.utc),
            content={
                "event_type": "execution_outcome",
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "pnl": pnl,
                "status": status,
            },
            metadata=metadata or {},
            validation_status=ValidationStatus.VALIDATED,
            operation_id=operation_id,
            agent_id=agent_id,
        )
        return self._store_and_audit(record, operation_id, agent_id)

    def capture_risk_assessment(
        self,
        *,
        assessment_type: str,
        result: str,
        circuit_breaker_state: str,
        risk_score: float,
        agent_id: str,
        operation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """Capture a risk assessment as Episodic Memory."""
        if not assessment_type:
            raise ValueError("assessment_type must not be empty")
        if result not in ("pass", "warn", "block"):
            raise ValueError(f"result must be pass/warn/block, got {result!r}")
        if circuit_breaker_state not in ("normal", "tripped", "cooldown"):
            raise ValueError(f"invalid circuit_breaker_state: {circuit_breaker_state!r}")
        if not 0 <= risk_score <= 100:
            raise ValueError(f"risk_score must be 0-100, got {risk_score}")

        record = MemoryRecord(
            memory_id=str(uuid.uuid4()),
            memory_type=MemoryType.EPISODIC,
            created_at=datetime.now(timezone.utc),
            content={
                "event_type": "risk_assessment",
                "assessment_type": assessment_type,
                "result": result,
                "circuit_breaker_state": circuit_breaker_state,
                "risk_score": risk_score,
            },
            metadata=metadata or {},
            validation_status=ValidationStatus.VALIDATED,
            operation_id=operation_id,
            agent_id=agent_id,
        )
        return self._store_and_audit(record, operation_id, agent_id)

    def capture_agent_decision(
        self,
        *,
        decision_type: str,
        input_summary: str,
        output_action: str,
        confidence: float,
        agent_id: str,
        operation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """Capture an agent decision as Episodic Memory."""
        if not decision_type:
            raise ValueError("decision_type must not be empty")
        if not input_summary:
            raise ValueError("input_summary must not be empty")
        if not output_action:
            raise ValueError("output_action must not be empty")
        if not 0 <= confidence <= 1:
            raise ValueError(f"confidence must be 0-1, got {confidence}")

        record = MemoryRecord(
            memory_id=str(uuid.uuid4()),
            memory_type=MemoryType.EPISODIC,
            created_at=datetime.now(timezone.utc),
            content={
                "event_type": "agent_decision",
                "decision_type": decision_type,
                "input_summary": input_summary,
                "output_action": output_action,
                "confidence": confidence,
            },
            metadata=metadata or {},
            validation_status=ValidationStatus.VALIDATED,
            operation_id=operation_id,
            agent_id=agent_id,
        )
        return self._store_and_audit(record, operation_id, agent_id)

    def _store_and_audit(
        self,
        record: MemoryRecord,
        operation_id: str,
        agent_id: str,
    ) -> MemoryRecord:
        """Store record via kernel and audit the outcome."""
        try:
            self._kernel.store(record)
            self._audit.record(AuditRecord(
                contract_version="1.0",
                event_id=str(uuid.uuid4()),
                event_type=AuditEventType.MEMORY_STORE,
                operation_id=operation_id,
                agent_id=agent_id,
                timestamp=datetime.now(timezone.utc),
                action=AuditAction.COMPLETED,
                resource=record.memory_id,
                result=AuditResult.SUCCESS,
                metadata={"source": "experience_engine", "memory_type": "episodic"},
            ))
            return record
        except Exception as exc:
            self._audit.record(AuditRecord(
                contract_version="1.0",
                event_id=str(uuid.uuid4()),
                event_type=AuditEventType.MEMORY_STORE,
                operation_id=operation_id,
                agent_id=agent_id,
                timestamp=datetime.now(timezone.utc),
                action=AuditAction.FAILED,
                resource=record.memory_id,
                result=AuditResult.FAILURE,
                metadata={"source": "experience_engine", "error": str(exc)},
            ))
            raise
