from intelligence.memory_system.memory_validation.validator import MemoryValidator
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)
from intelligence.memory_system.storage.interface import MemoryStorage


class MemoryKernel:
    """Coordinate controlled memory operations."""

    def __init__(self, storage: MemoryStorage) -> None:
        self._storage = storage
        self._validator = MemoryValidator()

    def store(self, record: MemoryRecord) -> None:
        validated_record = self._validator.validate(record)

        if validated_record.validation_status is not ValidationStatus.VALIDATED:
            raise ValueError("Only validated memory may be stored.")

        self._storage.store(validated_record)

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        if not memory_id:
            raise ValueError("memory_id must not be empty.")

        return self._storage.retrieve(memory_id)

    def delete(self, memory_id: str) -> bool:
        if not memory_id:
            raise ValueError("memory_id must not be empty.")

        return self._storage.delete(memory_id)

    @staticmethod
    def validate_type(
        record: MemoryRecord,
        expected_type: MemoryType,
    ) -> bool:
        return record.memory_type is expected_type
