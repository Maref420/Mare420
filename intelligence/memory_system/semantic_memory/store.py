from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
)


class SemanticMemoryStore:
    """Controlled interface for semantic memory."""

    def __init__(self, kernel: MemoryKernel) -> None:
        self._kernel = kernel

    def store(self, record: MemoryRecord) -> None:
        if record.memory_type is not MemoryType.SEMANTIC:
            raise ValueError("Semantic memory requires memory_type=semantic.")

        self._kernel.store(record)

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        return self._kernel.retrieve(memory_id)
