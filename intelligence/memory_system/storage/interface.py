from abc import ABC, abstractmethod

from intelligence.memory_system.models.memory_record import MemoryRecord


class MemoryStorage(ABC):
    """Abstract persistent storage boundary for validated memory records."""

    @abstractmethod
    def store(self, record: MemoryRecord) -> None:
        """Persist a memory record."""

    @abstractmethod
    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a memory record by identifier."""

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        """Delete a memory record when lifecycle policy permits it."""
