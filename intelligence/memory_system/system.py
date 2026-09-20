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
from intelligence.memory_system.episodic_memory.store import EpisodicMemoryStore
from intelligence.memory_system.experience_engine.engine import ExperienceEngine
from intelligence.memory_system.experience_engine.subscriber import ExperienceSubscriber
from intelligence.memory_system.forgetting.engine import MemoryForgettingEngine
from intelligence.memory_system.integration.context_injector import inject_memory_context
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import MemoryRecord
from intelligence.memory_system.procedural_memory.store import ProceduralMemoryStore
from intelligence.memory_system.retrieval_engine.engine import MemoryRetrievalEngine
from intelligence.memory_system.semantic_memory.store import SemanticMemoryStore
from intelligence.memory_system.storage.interface import MemoryStorage
from intelligence.memory_system.storage.supabase_storage import SupabaseStorage
from intelligence.memory_system.working_memory.store import WorkingMemoryStore

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
        supabase_url: str | None = None,
        supabase_key: str | None = None,
    ) -> None:
        # Priority: explicit storage > supabase credentials > in-memory fallback
        if storage is not None:
            self._storage = storage
        elif supabase_url and supabase_key:
            try:
                self._storage = SupabaseStorage(
                    supabase_url=supabase_url,
                    supabase_key=supabase_key,
                )
            except Exception as e:
                logger.warning(f"SUPABASE_INIT_FAILED_FALLBACK_TO_MEMORY: {e}")
                self._storage = InMemoryStorage()
        else:
            self._storage = InMemoryStorage()
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
        self._working_store = WorkingMemoryStore(kernel=self._kernel)
        self._episodic_store = EpisodicMemoryStore(kernel=self._kernel)
        self._semantic_store = SemanticMemoryStore(kernel=self._kernel)
        self._procedural_store = ProceduralMemoryStore(kernel=self._kernel)
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


    @property
    def working_store(self) -> WorkingMemoryStore:
        return self._working_store

    @property
    def episodic_store(self) -> EpisodicMemoryStore:
        return self._episodic_store

    @property
    def semantic_store(self) -> SemanticMemoryStore:
        return self._semantic_store

    @property
    def procedural_store(self) -> ProceduralMemoryStore:
        return self._procedural_store

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


    def run_consolidation_cycle(
        self,
        source_memory_id: str,
        operation_id: str,
        agent_id: str,
    ) -> bool:
        """
        Consolidate validated episodic memory into semantic knowledge.

        Governed by:
        - lifecycle-policy.yaml: consolidation elevates episodic to semantic
        - ConsolidationEngine validates source is EPISODIC + VALIDATED
        - NEVER writes directly to storage (routes through Kernel)

        Args:
            source_memory_id: ID of the episodic memory record to consolidate.
            operation_id: Trace identifier for audit.
            agent_id: Agent requesting consolidation.

        Returns:
            True if consolidation succeeded, False otherwise.
        """
        try:
            source_record = self._kernel.retrieve(source_memory_id)
            if source_record is None:
                logger.warning(
                    "CONSOLIDATION_SKIPPED",
                    extra={"reason": "source_not_found", "memory_id": source_memory_id},
                )
                return False

            result = self._consolidation_engine.consolidate(
                source_record,
                operation_id=operation_id,
                agent_id=agent_id,
            )
            logger.info(
                "CONSOLIDATION_COMPLETED",
                extra={
                    "source_id": source_memory_id,
                    "semantic_id": result.memory_id,
                    "operation_id": operation_id,
                },
            )
            return True
        except ValueError as e:
            logger.warning(
                "CONSOLIDATION_REJECTED",
                extra={"memory_id": source_memory_id, "reason": str(e)},
            )
            return False
        except Exception as e:
            logger.error(
                "CONSOLIDATION_FAILED",
                extra={"memory_id": source_memory_id, "error": str(e)},
            )
            return False

    def shutdown(self) -> None:
        """Graceful shutdown hook."""
        logger.info("MEMORY_SYSTEM_SHUTDOWN")
