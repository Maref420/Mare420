"""
Pipeline Governance Hook for Atlas AI.
Bridges the Signal Producer/Canceler layer with the Memory System layer.
Instantiates MemorySystem and provides interception points for the pipeline.

Governed by:
- ATLAS Protocol Rule 12 (Minimal Blast Radius)
- lifecycle-policy.yaml: operations.store.kernel_required: true
- lifecycle-policy.yaml: audit_logging_required: true
- Read-Before-Decide & Write-After-Execute principles
"""
from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from intelligence.agent_control_plane.audit.models import (
    AuditAction,
    AuditEventType,
    AuditRecord,
    AuditResult,
)
from intelligence.agent_control_plane.policy.decision_evaluator import (
    PolicyDecision,
)
from intelligence.contracts.unified_decision_proposal import DecisionProposal
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)
from intelligence.memory_system.system import MemorySystem

logger = logging.getLogger(__name__)


class PipelineGovernanceHook:
    """
    Singleton-style hook that bridges the signal pipeline with memory.
    Must be initialized once at pipeline startup and passed to components
    that need memory read/write access.
    """

    _instance: PipelineGovernanceHook | None = None
    _memory_system: MemorySystem | None = None
    _initialized: bool = False

    @classmethod
    def initialize(cls, **kwargs: Any) -> PipelineGovernanceHook:
        """
        Initialize the governance hook and underlying MemorySystem.
        Safe to call multiple times; only initializes once.
        """
        if cls._instance is None:
            cls._instance = cls()
        if not cls._initialized:
            cls._memory_system = MemorySystem(**kwargs)
            cls._initialized = True
            logger.info("PIPELINE_GOVERNANCE_HOOK_INITIALIZED")
        return cls._instance

    @classmethod
    def get_memory_system(cls) -> MemorySystem:
        """Access the unified memory system."""
        if cls._memory_system is None:
            raise RuntimeError(
                "PipelineGovernanceHook not initialized. Call initialize() first."
            )
        return cls._memory_system

    @classmethod
    def inject_context_before_policy(
        cls, proposal: DecisionProposal
    ) -> DecisionProposal:
        """
        INTERCEPTION POINT 1: Read-Before-Decide.
        Called by pipeline BEFORE PolicyEvaluator.evaluate_proposal().
        Injects multi-tier memory context into the proposal.
        """
        if cls._memory_system is None:
            logger.warning("CONTEXT_INJECTION_SKIPPED: MemorySystem not initialized")
            return proposal

        with contextlib.suppress(Exception):
            enriched: DecisionProposal = cls._memory_system.inject_context(proposal)
            logger.info(
                "PRE_POLICY_CONTEXT_INJECTED",
                extra={"proposal_id": proposal.proposal_id},
            )
            return enriched

        return proposal

    @classmethod
    def persist_cancellation(
        cls,
        proposal: DecisionProposal,
        decision: PolicyDecision,
        reason: str,
    ) -> None:
        """
        INTERCEPTION POINT 2: Cancel-Memory-Awareness.
        Called by Dispatcher when decision != ALLOW.
        Persists the cancellation reason into Working Memory through the
        proper WorkingMemoryStore Type Gate, and generates a compliant
        AuditRecord per lifecycle-policy.yaml.
        """
        if cls._memory_system is None:
            return

        operation_id = f"cancel-{uuid.uuid4().hex[:8]}"
        agent_id = "pipeline-governance-hook"
        memory_id = f"working_cancel_{proposal.proposal_id}"
        resource = f"memory:working:{memory_id}"
        timestamp = datetime.now(UTC)
        audit_result = AuditResult.FAILURE

        try:
            cancellation_record = MemoryRecord(
                memory_id=memory_id,
                memory_type=MemoryType.WORKING,
                created_at=timestamp,
                content={
                    "event_type": "signal_cancellation",
                    "symbol": proposal.target_strategy,
                    "action": proposal.proposed_action,
                    "decision": decision.value,
                    "reason": reason,
                    "survival_score": proposal.adversarial_report.survival_score,
                },
                metadata={
                    "source_proposal_id": proposal.proposal_id,
                    "expires_at": timestamp.timestamp() + 86400,
                },
                validation_status=ValidationStatus.VALIDATED,
                operation_id=operation_id,
                agent_id=agent_id,
                source="pipeline_governance_hook",
                source_type="cancellation_event",
                regime="unknown",
            )

            # Route through WorkingMemoryStore Type Gate (NOT kernel.store directly)
            cls._memory_system.working_store.store(cancellation_record)
            audit_result = AuditResult.SUCCESS

            logger.info(
                "CANCELLATION_PERSISTED",
                extra={
                    "proposal_id": proposal.proposal_id,
                    "decision": decision.value,
                    "reason": reason,
                    "memory_id": memory_id,
                },
            )

        except ValueError as e:
            logger.error(
                "CANCELLATION_VALIDATION_REJECTED",
                extra={"proposal_id": proposal.proposal_id, "error": str(e)},
            )
        except Exception as e:
            logger.error(
                "CANCELLATION_PERSISTENCE_FAILED",
                extra={"proposal_id": proposal.proposal_id, "error": str(e)},
            )

        # Generate compliant AuditRecord per audit_logging_required policy
        cls._emit_audit_record(
            event_id=f"audit-{uuid.uuid4().hex[:8]}",
            event_type=AuditEventType.MEMORY_STORE,
            operation_id=operation_id,
            agent_id=agent_id,
            timestamp=timestamp,
            action=AuditAction.COMPLETED if audit_result == AuditResult.SUCCESS else AuditAction.FAILED,
            resource=resource,
            result=audit_result,
            metadata={
                "proposal_id": proposal.proposal_id,
                "decision": decision.value,
                "reason": reason,
            },
        )

    @classmethod
    def _emit_audit_record(
        cls,
        *,
        event_id: str,
        event_type: AuditEventType,
        operation_id: str,
        agent_id: str,
        timestamp: datetime,
        action: AuditAction,
        resource: str,
        result: AuditResult,
        metadata: dict[str, Any],
    ) -> None:
        """
        Construct and emit an AuditRecord through the configured AuditSink.
        Governed by: lifecycle-policy.yaml -> traceability requirements.
        """
        if cls._memory_system is None:
            return

        with contextlib.suppress(Exception):
            audit_record = AuditRecord(
                contract_version="1.0",
                event_id=event_id,
                event_type=event_type,
                operation_id=operation_id,
                agent_id=agent_id,
                timestamp=timestamp,
                action=action,
                resource=resource,
                result=result,
                metadata=metadata,
            )
            cls._memory_system.audit_sink.record(audit_record)
            logger.info(
                "AUDIT_RECORD_EMITTED",
                extra={"event_id": event_id, "event_type": event_type.value, "result": result.value},
            )

    @classmethod
    async def start_outcome_listener(cls) -> bool:
        """
        INTERCEPTION POINT 3: Write-After-Execute.
        Verifies ExperienceSubscriber availability for NATS outcome capture.
        """
        if cls._memory_system is None:
            logger.warning("OUTCOME_LISTENER_SKIPPED: MemorySystem not initialized")
            return False

        with contextlib.suppress(Exception):
            _ = cls._memory_system.experience_subscriber
            logger.info("OUTCOME_LISTENER_READY: ExperienceSubscriber available")
            return True

        return False

    @classmethod
    def shutdown(cls) -> None:
        """Graceful shutdown of memory system."""
        if cls._memory_system is not None:
            cls._memory_system.shutdown()
            cls._initialized = False
            cls._instance = None
            logger.info("PIPELINE_GOVERNANCE_HOOK_SHUTDOWN")
