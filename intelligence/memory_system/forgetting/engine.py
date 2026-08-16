from uuid import uuid4

from intelligence.agent_control_plane.audit.interface import AuditSink
from intelligence.agent_control_plane.audit.models import (
    AuditAction,
    AuditEventType,
    AuditRecord,
    AuditResult,
)
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel


class MemoryForgettingEngine:
    """Controlled lifecycle boundary for memory removal."""

    def __init__(
        self,
        kernel: MemoryKernel,
        audit_sink: AuditSink,
    ) -> None:
        self._kernel = kernel
        self._audit_sink = audit_sink

    def forget(
        self,
        memory_id: str,
        *,
        operation_id: str,
        agent_id: str,
    ) -> bool:
        if not memory_id:
            raise ValueError("memory_id must not be empty.")

        if not operation_id:
            raise ValueError("operation_id must not be empty.")

        if not agent_id:
            raise ValueError("agent_id must not be empty.")

        event_id = str(uuid4())

        self._audit_sink.record(
            AuditRecord(
                contract_version="1.0",
                event_id=event_id,
                event_type=AuditEventType.MEMORY_FORGET,
                operation_id=operation_id,
                agent_id=agent_id,
                timestamp=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
                action=AuditAction.REQUESTED,
                resource=memory_id,
                result=AuditResult.SUCCESS,
                metadata={},
            )
        )

        try:
            deleted = self._kernel.delete(memory_id)
        except Exception:
            self._audit_sink.record(
                AuditRecord(
                    contract_version="1.0",
                    event_id=str(uuid4()),
                    event_type=AuditEventType.MEMORY_FORGET,
                    operation_id=operation_id,
                    agent_id=agent_id,
                    timestamp=__import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ),
                    action=AuditAction.FAILED,
                    resource=memory_id,
                    result=AuditResult.FAILURE,
                    metadata={},
                )
            )
            raise

        self._audit_sink.record(
            AuditRecord(
                contract_version="1.0",
                event_id=str(uuid4()),
                event_type=AuditEventType.MEMORY_FORGET,
                operation_id=operation_id,
                agent_id=agent_id,
                timestamp=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
                action=AuditAction.COMPLETED,
                resource=memory_id,
                result=AuditResult.SUCCESS,
                metadata={},
            )
        )

        return deleted

    def exists(self, memory_id: str) -> bool:
        if not memory_id:
            raise ValueError("memory_id must not be empty.")

        return self._kernel.retrieve(memory_id) is not None
