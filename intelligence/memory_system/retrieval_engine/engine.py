from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
)
from intelligence.memory_system.storage.interface import MemoryStorage


class MemoryRetrievalEngine:
    """Controlled retrieval boundary for persisted memory."""

    def __init__(self, storage: MemoryStorage) -> None:
        self._storage = storage

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        if not memory_id:
            raise ValueError("memory_id must not be empty.")

        record = self._storage.retrieve(memory_id)

        if record is None:
            return None

        if record.memory_type not in (
            MemoryType.WORKING,
            MemoryType.EPISODIC,
            MemoryType.SEMANTIC,
            MemoryType.PROCEDURAL,
        ):
            raise ValueError("Unsupported memory type.")

        return record
