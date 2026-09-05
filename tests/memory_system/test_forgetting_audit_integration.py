"""Integration tests for MemoryForgettingEngine audit behavior.

Updated to match governed API:
- forget() returns bool (not raises)
- Single audit event with real result (SUCCESS or FAILURE)
- retrieve() must return a valid record for deletion to proceed
"""
import unittest
from datetime import datetime, timezone

from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
from intelligence.memory_system.forgetting.engine import MemoryForgettingEngine
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)


def make_episodic_record(memory_id: str) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=MemoryType.EPISODIC,
        created_at=datetime.now(timezone.utc),
        content={"test": True},
        metadata={},
        validation_status=ValidationStatus.VALIDATED,
        operation_id="op-create",
        agent_id="agent-test",
    )


class FakeStorage:
    def __init__(self) -> None:
        self.records: dict[str, MemoryRecord] = {}
        self.deleted: list[str] = []

    def store(self, record: MemoryRecord) -> None:
        self.records[record.memory_id] = record

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        return self.records.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        if memory_id in self.records:
            self.deleted.append(memory_id)
            del self.records[memory_id]
            return True
        return False


class FailingStorage(FakeStorage):
    """Storage that raises on delete to simulate infrastructure failure."""

    def delete(self, memory_id: str) -> bool:
        self.deleted.append(memory_id)
        raise RuntimeError("storage failure")


class TestForgettingAuditIntegration(unittest.TestCase):
    def test_successful_forget_is_audited(self) -> None:
        storage = FakeStorage()
        storage.store(make_episodic_record("memory-001"))
        kernel = MemoryKernel(storage)
        audit = InMemoryAuditSink()
        engine = MemoryForgettingEngine(kernel, audit)

        result = engine.forget(
            "memory-001",
            operation_id="op-001",
            agent_id="agent-001",
            explicit_policy_id="memory-lifecycle-policy:v1:test",
        )

        self.assertTrue(result)
        self.assertEqual(storage.deleted, ["memory-001"])
        events = audit.events()
        self.assertGreaterEqual(len(events), 1)
        # At least one audit event must exist with correct traceability
        forget_events = [
            e for e in events if e.event_type.value == "memory.forget"
        ]
        self.assertGreaterEqual(len(forget_events), 1)
        last_event = forget_events[-1]
        self.assertEqual(last_event.result.value, "success")
        self.assertEqual(last_event.operation_id, "op-001")
        self.assertEqual(last_event.agent_id, "agent-001")
        self.assertEqual(last_event.resource, "memory-001")

    def test_failed_forget_is_audited_as_failure_not_exception(self) -> None:
        """Governed behavior: storage failure is caught, audited as FAILURE,
        and forget() returns False instead of propagating the exception."""
        storage = FailingStorage()
        storage.store(make_episodic_record("memory-002"))
        kernel = MemoryKernel(storage)
        audit = InMemoryAuditSink()
        engine = MemoryForgettingEngine(kernel, audit)

        # Must NOT raise — governed API returns bool
        result = engine.forget(
            "memory-002",
            operation_id="op-002",
            agent_id="agent-002",
            explicit_policy_id="memory-lifecycle-policy:v1:test",
        )

        self.assertFalse(result)
        events = audit.events()
        forget_events = [
            e for e in events if e.event_type.value == "memory.forget"
        ]
        self.assertGreaterEqual(len(forget_events), 1)
        last_event = forget_events[-1]
        self.assertEqual(last_event.result.value, "failure")
        self.assertEqual(last_event.operation_id, "op-002")
        self.assertEqual(last_event.agent_id, "agent-002")
        self.assertEqual(last_event.resource, "memory-002")
        self.assertIn("storage_delete_exception", last_event.metadata.get("reason", ""))

    def test_missing_record_is_audited_as_failure(self) -> None:
        """Attempting to forget a non-existent record audits FAILURE."""
        storage = FakeStorage()
        kernel = MemoryKernel(storage)
        audit = InMemoryAuditSink()
        engine = MemoryForgettingEngine(kernel, audit)

        result = engine.forget(
            "nonexistent",
            operation_id="op-003",
            agent_id="agent-003",
        )

        self.assertFalse(result)
        events = audit.events()
        forget_events = [
            e for e in events if e.event_type.value == "memory.forget"
        ]
        self.assertGreaterEqual(len(forget_events), 1)
        last_event = forget_events[-1]
        self.assertEqual(last_event.result.value, "failure")
        self.assertEqual(last_event.metadata.get("reason"), "memory_not_found")


if __name__ == "__main__":
    unittest.main()
