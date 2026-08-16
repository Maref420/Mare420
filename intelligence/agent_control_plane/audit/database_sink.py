import os

from supabase import Client, create_client

from intelligence.agent_control_plane.audit.interface import AuditSink
from intelligence.agent_control_plane.audit.models import AuditRecord


class DatabaseAuditSink(AuditSink):
    """Supabase-backed persistent audit sink."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )

    def record(self, event: AuditRecord) -> None:
        payload = {
            "event_id": event.event_id,
            "contract_version": event.contract_version,
            "event_type": event.event_type.value,
            "operation_id": event.operation_id,
            "agent_id": event.agent_id,
            "timestamp": event.timestamp.isoformat(),
            "action": event.action.value,
            "resource": event.resource,
            "result": event.result.value,
            "metadata": event.metadata,
        }

        self._client.table("audit_events").insert(payload).execute()
