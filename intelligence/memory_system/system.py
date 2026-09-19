"""
Unified Memory System Facade for Atlas AI.
Wires together all internal Memory Layer components into a single,
cohesive system following governance rules strictly.

Governed by:
- contracts/schemas/memory/memory-experience-event-v1.json
- governance/policies/memory/lifecycle-policy.yaml
- Architecture Review: ARCH-REVIEW-002
- ATLAS Protocol Rule 6 (Architecture) & Rule 12 (Minimal Blast Radius)

Rules Enforced:
- NEVER writes directly to storage (ALWAYS through MemoryKernel)
- ALWAYS includes operation_id + agent_id for traceability
- ALWAYS audits every capture attempt via AuditSink
- direct_storage_access: forbidden
- cross_language_direct_call: forbidden
"""
from __future__ import annotations

import logging
from typing import Any

from intelligence.agent_control_plane.audit.interface import AuditSink
from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
from intelligence.memory_system.consolidation.engine import MemoryConsolidationEngine
from intelligence.memory_system.experience_engine.engine import ExperienceEngine
from intelligence.memory_system.experience_engine.subscriber import ExperienceSubscriber
from intelligence.memory_system.forgetting.engine import MemoryForgettingEngine
from intelligence.memory_system.integration.context_injector import inject_memory_context
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import MemoryRecord
from intelligence.memory_system.retrieval_engine.engine import MemoryRetrievalEngine
from intelligence.memory_system.storage.interface import MemoryStorage

logger = logging.getLogger(__name__)


class InMemoryStorage(MemoryStorage):
    """
    Default in-memory implementation of MemoryStorage ABC.
    Used when no persistent storage backend is configured.
    Governed by: lifecycle-policy.yaml -> operations.store.kernel_required: true
    """

    def __init__(self) -> None:
        self._store: dict[str, MemoryRecord] = {}

    def store(self, record: MemoryRecord) -> None:
        self._store[record.memory_id] = record

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        return self._store.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        if memory_id in self._store:
            del self._store[memory_id]
            return True
        return False


class MemorySystem:
    """
    Unified Facade for the entire Memory Layer.
    Single authorized entry point for initializing and accessing memory subsystems.
    """

    def __init__(
        self,
        storage: MemoryStorage | None = None,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self._storage = storage or InMemoryStorage()
        self._audit_sink = audit_sink or InMemoryAuditSink()
        self._kernel = MemoryKernel(storage=self._storage)
        self._experience_engine = ExperienceEngine(
            kernel=self._kernel, audit_sink=self._audit_sink
        )
        self._forgetting_engine = MemoryForgettingEngine(
            kernel=self._kernel, audit_sink=self._audit_sink
        )
        self._consolidation_engine = MemoryConsolidationEngine(kernel=self._kernel)
        self._retrieval_engine = MemoryRetrievalEngine(storage=self._storage)
        self._experience_subscriber = ExperienceSubscriber()
        logger.info("MEMORY_SYSTEM_INITIALIZED")

    @property
    def kernel(self) -> MemoryKernel:
        return self._kernel

    @property
    def experience_engine(self) -> ExperienceEngine:
        return self._experience_engine

    @property
    def forgetting_engine(self) -> MemoryForgettingEngine:
        return self._forgetting_engine

    @property
    def consolidation_engine(self) -> MemoryConsolidationEngine:
        return self._consolidation_engine

    @property
    def retrieval_engine(self) -> MemoryRetrievalEngine:
        return self._retrieval_engine

    @property
    def experience_subscriber(self) -> ExperienceSubscriber:
        return self._experience_subscriber

    @property
    def audit_sink(self) -> AuditSink:
        return self._audit_sink

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
        """Capture execution outcome as Episodic Memory via ExperienceEngine."""
        return self._experience_engine.capture_execution_outcome(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            pnl=pnl,
            status=status,
            agent_id=agent_id,
            operation_id=operation_id,
            metadata=metadata,
        )

    def inject_context(self, proposal: Any) -> Any:
        """Read memory context before Policy Evaluation."""
        return inject_memory_context(proposal, self._kernel)

    def retrieve_memory(self, memory_id: str) -> MemoryRecord | None:
        """Unified retrieval through kernel validation."""
        return self._kernel.retrieve(memory_id)

    def run_forgetting_cycle(
        self,
        memory_id: str,
        operation_id: str,
        agent_id: str,
    ) -> bool:
        """
        Execute forgetting cycle on working memory.
        Governed by: lifecycle-policy.yaml -> working.forgetting.automatic: allowed
        """
        try:
            result = self._forgetting_engine.forget_if_expired_working_memory(
                memory_id,
                operation_id=operation_id,
                agent_id=agent_id,
            )
            logger.info(
                "FORGETTING_CYCLE_COMPLETED",
                extra={
                    "memory_id": memory_id,
                    "operation_id": operation_id,
                    "result": result,
                },
            )
            return result
        except Exception as e:
            logger.error(
                "FORGETTING_CYCLE_FAILED",
                extra={"memory_id": memory_id, "error": str(e)},
            )
            return False

    def shutdown(self) -> None:
        """Graceful shutdown hook."""
        logger.info("MEMORY_SYSTEM_SHUTDOWN")
