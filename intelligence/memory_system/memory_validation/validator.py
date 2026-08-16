from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    ValidationStatus,
)


class MemoryValidator:
    """Validate memory records before persistence."""

    def validate(self, record: MemoryRecord) -> MemoryRecord:
        if not record.memory_id:
            raise ValueError("memory_id must not be empty.")

        if not record.operation_id:
            raise ValueError("operation_id must not be empty.")

        if not record.agent_id:
            raise ValueError("agent_id must not be empty.")

        if record.validation_status is ValidationStatus.REJECTED:
            raise ValueError("Rejected memory cannot be persisted.")

        return record
