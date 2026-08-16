import unittest

from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
from intelligence.memory_system.forgetting.engine import MemoryForgettingEngine
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel


class FakeStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def store(self, record):
        raise NotImplementedError

    def retrieve(self, memory_id):
        return None

    def delete(self, memory_id: str) -> bool:
        self.deleted.append(memory_id)
        return True


class FailingStorage(FakeStorage):
    def delete(self, memory_id: str) -> bool:
        self.deleted.append(memory_id)
        raise RuntimeError("storage failure")


class TestForgettingAuditIntegration(unittest.TestCase):
    def test_successful_forget_is_audited(self) -> None:
        storage = FakeStorage()
        kernel = MemoryKernel(storage)
        audit = InMemoryAuditSink()
        engine = MemoryForgettingEngine(kernel, audit)

        result = engine.forget(
            "memory-001",
            operation_id="op-001",
            agent_id="agent-001",
        )

        self.assertTrue(result)
        self.assertEqual(storage.deleted, ["memory-001"])

        events = audit.events()
        self.assertEqual(len(events), 2)

        self.assertEqual(events[0].action.value, "requested")
        self.assertEqual(events[0].result.value, "success")

        self.assertEqual(events[1].action.value, "completed")
        self.assertEqual(events[1].result.value, "success")

        for event in events:
            self.assertEqual(event.event_type.value, "memory.forget")
            self.assertEqual(event.operation_id, "op-001")
            self.assertEqual(event.agent_id, "agent-001")
            self.assertEqual(event.resource, "memory-001")

    def test_failed_forget_is_audited(self) -> None:
        storage = FailingStorage()
        kernel = MemoryKernel(storage)
        audit = InMemoryAuditSink()
        engine = MemoryForgettingEngine(kernel, audit)

        with self.assertRaises(RuntimeError):
            engine.forget(
                "memory-002",
                operation_id="op-002",
                agent_id="agent-002",
            )

        events = audit.events()
        self.assertEqual(len(events), 2)

        self.assertEqual(events[0].action.value, "requested")
        self.assertEqual(events[1].action.value, "failed")
        self.assertEqual(events[1].result.value, "failure")


if __name__ == "__main__":
    unittest.main()
