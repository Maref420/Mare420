from intelligence.agent_control_plane.audit.interface import AuditSink
from intelligence.agent_control_plane.audit.models import AuditRecord


class InMemoryAuditSink(AuditSink):
    """Deterministic audit sink for tests and local execution."""

    def __init__(self) -> None:
        self._events: list[AuditRecord] = []

    def record(self, event: AuditRecord) -> None:
        self._events.append(event)

    def events(self) -> tuple[AuditRecord, ...]:
        return tuple(self._events)
