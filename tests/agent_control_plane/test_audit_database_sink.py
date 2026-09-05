import unittest
from datetime import UTC, datetime

from intelligence.agent_control_plane.audit.database_sink import DatabaseAuditSink
from intelligence.agent_control_plane.audit.models import (
    AuditAction,
    AuditEventType,
    AuditRecord,
    AuditResult,
)


class FakeResponse:
    def execute(self) -> "FakeResponse":
        return self


class FakeTable:
    def __init__(self) -> None:
        self.inserted_payload = None

    def insert(self, payload: dict) -> FakeResponse:
        self.inserted_payload = payload
        return FakeResponse()


class FakeClient:
    def __init__(self) -> None:
        self.table_instance = FakeTable()
        self.table_name = None

    def table(self, name: str) -> FakeTable:
        self.table_name = name
        return self.table_instance


class TestDatabaseAuditSink(unittest.TestCase):
    def test_record_persists_complete_audit_payload(self) -> None:
        client = FakeClient()
        sink = DatabaseAuditSink(client=client)

        timestamp = datetime(2026, 8, 18, 12, 30, 45, tzinfo=UTC)

        event = AuditRecord(
            contract_version="1.0",
            event_id="event-001",
            event_type=AuditEventType.COMMUNICATION_SEND,
            operation_id="operation-001",
            agent_id="agent-001",
            timestamp=timestamp,
            action=AuditAction.COMPLETED,
            resource="agent-002",
            result=AuditResult.SUCCESS,
            metadata={"message_type": "request"},
        )

        sink.record(event)

        self.assertEqual(client.table_name, "audit_events")
        self.assertEqual(
            client.table_instance.inserted_payload,
            {
                "event_id": "event-001",
                "contract_version": "1.0",
                "event_type": "communication.send",
                "operation_id": "operation-001",
                "agent_id": "agent-001",
                "timestamp": timestamp.isoformat(),
                "action": "completed",
                "resource": "agent-002",
                "result": "success",
                "metadata": {"message_type": "request"},
            },
        )


if __name__ == "__main__":
    unittest.main()
