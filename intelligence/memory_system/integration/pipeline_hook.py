"""
Pipeline Governance Hook for Atlas AI.
Bridges the Signal Producer/Canceler layer with the Memory System layer.
Instantiates MemorySystem and provides interception points for the pipeline.

Governed by:
- ATLAS Protocol Rule 12 (Minimal Blast Radius)
- lifecycle-policy.yaml: operations.store.kernel_required: true
- Read-Before-Decide & Write-After-Execute principles
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from intelligence.agent_control_plane.policy.decision_evaluator import (
    PolicyDecision,
)
from intelligence.contracts.unified_decision_proposal import DecisionProposal
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

        try:
            enriched: DecisionProposal = cls._memory_system.inject_context(proposal)
            logger.info(
                "PRE_POLICY_CONTEXT_INJECTED",
                extra={"proposal_id": proposal.proposal_id},
            )
            return enriched
        except Exception as e:
            logger.error(
                "PRE_POLICY_INJECTION_FAILED",
                extra={"proposal_id": proposal.proposal_id, "error": str(e)},
            )
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
        Persists the cancellation reason into Working Memory so future
        signals for the same symbol/action can learn from this denial.
        """
        if cls._memory_system is None:
            return

        try:
            operation_id = f"cancel-{uuid.uuid4().hex[:8]}"
            agent_id = "pipeline-governance-hook"

            from intelligence.memory_system.models.memory_record import (
                MemoryRecord,
                MemoryType,
                ValidationStatus,
            )

            cancellation_record = MemoryRecord(
                memory_id=f"working_cancel_{proposal.proposal_id}",
                memory_type=MemoryType.WORKING,
                created_at=datetime.now(UTC),
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
                    "expires_at": (
                        datetime.now(UTC).timestamp() + 86400
                    ),
                },
                validation_status=ValidationStatus.VALIDATED,
                operation_id=operation_id,
                agent_id=agent_id,
                source="pipeline_governance_hook",
                source_type="cancellation_event",
                regime="unknown",
            )

            cls._memory_system.kernel.store(cancellation_record)
            logger.info(
                "CANCELLATION_PERSISTED",
                extra={
                    "proposal_id": proposal.proposal_id,
                    "decision": decision.value,
                    "reason": reason,
                    "memory_id": cancellation_record.memory_id,
                },
            )
        except Exception as e:
            logger.error(
                "CANCELLATION_PERSISTENCE_FAILED",
                extra={"proposal_id": proposal.proposal_id, "error": str(e)},
            )

    @classmethod
    async def start_outcome_listener(cls) -> bool:
        """
        INTERCEPTION POINT 3: Write-After-Execute.
        Starts the ExperienceSubscriber to listen for execution outcomes
        on NATS and persist them via ExperienceEngine.
        """
        if cls._memory_system is None:
            logger.warning("OUTCOME_LISTENER_SKIPPED: MemorySystem not initialized")
            return False

        try:
            _ = cls._memory_system.experience_subscriber
            logger.info("OUTCOME_LISTENER_READY: ExperienceSubscriber available")
            return True
        except Exception as e:
            logger.error(f"OUTCOME_LISTENER_FAILED: {e}")
            return False

    @classmethod
    def shutdown(cls) -> None:
        """Graceful shutdown of memory system."""
        if cls._memory_system is not None:
            cls._memory_system.shutdown()
            cls._initialized = False
            cls._instance = None
            logger.info("PIPELINE_GOVERNANCE_HOOK_SHUTDOWN")
