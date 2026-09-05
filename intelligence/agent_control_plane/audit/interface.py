from abc import ABC, abstractmethod

from intelligence.agent_control_plane.audit.models import AuditRecord


class AuditSink(ABC):
    """Controlled boundary for immutable audit persistence."""

    @abstractmethod
    def record(self, event: AuditRecord) -> None:
        """Persist an audit event."""
