from datetime import datetime, timezone

from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)


class MemoryConsolidationEngine:
    """Convert validated episodic memory into semantic knowledge."""

    def __init__(self, kernel: MemoryKernel) -> None:
        self._kernel = kernel

    def consolidate(
        self,
        source: MemoryRecord,
        *,
        operation_id: str,
        agent_id: str,
    ) -> MemoryRecord:
        if source.memory_type is not MemoryType.EPISODIC:
            raise ValueError(
                "Consolidation requires episodic source memory."
            )

        if source.validation_status is not ValidationStatus.VALIDATED:
            raise ValueError(
                "Only validated episodic memory may be consolidated."
            )

        if not operation_id:
            raise ValueError("operation_id must not be empty.")

        if not agent_id:
            raise ValueError("agent_id must not be empty.")

        consolidated = MemoryRecord(
            memory_id=f"semantic:{source.memory_id}",
            memory_type=MemoryType.SEMANTIC,
            created_at=datetime.now(timezone.utc),
            content={
                "source_memory_id": source.memory_id,
                "knowledge": source.content,
            },
            metadata={
                "consolidated_from": source.memory_id,
                "source_memory_type": source.memory_type.value,
            },
            validation_status=ValidationStatus.VALIDATED,
            operation_id=operation_id,
            agent_id=agent_id,
        )

        self._kernel.store(consolidated)
        return consolidated
