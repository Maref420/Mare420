import unittest
from datetime import UTC, datetime

from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
from intelligence.agent_control_plane.gateway.gateway import AgentGateway
from intelligence.agent_control_plane.identity.models import (
    AgentIdentity,
    AgentStatus,
)
from intelligence.agent_control_plane.permissions.engine import PermissionEngine
from intelligence.agent_control_plane.permissions.models import (
    Capability,
    PermissionSet,
)
from intelligence.agent_control_plane.policy.engine import AgentPolicyEngine
from intelligence.agent_control_plane.registry.registry import AgentRegistry
from intelligence.memory_system.forgetting.engine import MemoryForgettingEngine
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)
from intelligence.memory_system.retrieval_engine.engine import MemoryRetrievalEngine


class FakeStorage:
    def __init__(self) -> None:
        self.records: dict[str, MemoryRecord] = {}

    def store(self, record: MemoryRecord) -> None:
        self.records[record.memory_id] = record

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        return self.records.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        return self.records.pop(memory_id, None) is not None


class TestAgentGateway(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = FakeStorage()
        self.kernel = MemoryKernel(self.storage)
        self.audit = InMemoryAuditSink()

        self.registry = AgentRegistry()
        self.registry.register(
            AgentIdentity(
                agent_id="atlas-agent",
                version="1.0",
                status=AgentStatus.VALIDATED,
            )
        )

        self.permissions = PermissionEngine()
        self.permissions.grant(
            PermissionSet(
                agent_id="atlas-agent",
                capabilities=frozenset(
                    {
                        Capability.MEMORY_RETRIEVE,
                        Capability.MEMORY_STORE,
                        Capability.MEMORY_FORGET,
                    }
                ),
            )
        )

        self.gateway = AgentGateway(
            registry=self.registry,
            permissions=self.permissions,
            policy=AgentPolicyEngine(),
            kernel=self.kernel,
            audit_sink=self.audit,
            forgetting=MemoryForgettingEngine(
                self.kernel,
                self.audit,
            ),
            retrieval=MemoryRetrievalEngine(self.storage),
        )

    def _record(self) -> MemoryRecord:
        return MemoryRecord(
            memory_id="memory-001",
            memory_type=MemoryType.SEMANTIC,
            created_at=datetime.now(UTC),
            content={"knowledge": "validated"},
            metadata={},
            validation_status=ValidationStatus.VALIDATED,
            operation_id="store-op",
            agent_id="atlas-agent",
        )

    def test_store_and_retrieve_through_gateway(self) -> None:
        record = self._record()

        self.gateway.store(
            "atlas-agent",
            record,
            operation_id="store-op",
        )

        retrieved = self.gateway.retrieve(
            "atlas-agent",
            "memory-001",
            operation_id="retrieve-op",
        )

        self.assertEqual(retrieved, record)

        events = self.audit.events()
        self.assertEqual(len(events), 4)
        self.assertEqual(events[0].event_type, "memory.store")
        self.assertEqual(events[1].event_type, "memory.store")
        self.assertEqual(events[2].event_type, "memory.retrieve")
        self.assertEqual(events[3].event_type, "memory.retrieve")

    def test_forget_uses_controlled_lifecycle(self) -> None:
        self.kernel.store(self._record())

        result = self.gateway.forget(
            "atlas-agent",
            "memory-001",
            operation_id="forget-op",
        )

        self.assertTrue(result)
        self.assertNotIn("memory-001", self.storage.records)

        events = self.audit.events()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_type, "memory.forget")
        self.assertEqual(events[0].action.value, "requested")
        self.assertEqual(events[1].action.value, "completed")

    def test_unknown_agent_is_rejected(self) -> None:
        with self.assertRaises(PermissionError):
            self.gateway.retrieve(
                "unknown-agent",
                "memory-001",
                operation_id="op-unknown",
            )

    def test_suspended_agent_is_rejected(self) -> None:
        self.registry.replace(
            AgentIdentity(
                agent_id="atlas-agent",
                version="1.0",
                status=AgentStatus.SUSPENDED,
            )
        )

        with self.assertRaises(PermissionError):
            self.gateway.retrieve(
                "atlas-agent",
                "memory-001",
                operation_id="op-suspended",
            )

    def test_unknown_agent_rejection_is_audited(self) -> None:
        with self.assertRaises(PermissionError):
            self.gateway.retrieve(
                "unknown-agent",
                "memory-001",
                operation_id="op-audit-unknown",
            )

        events = self.audit.events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "memory.retrieve")
        self.assertEqual(events[0].action.value, "failed")
        self.assertEqual(events[0].result.value, "failure")
        self.assertEqual(events[0].operation_id, "op-audit-unknown")

    def test_missing_capability_is_rejected(self) -> None:
        self.permissions.grant(
            PermissionSet(
                agent_id="atlas-agent",
                capabilities=frozenset(),
            )
        )

        with self.assertRaises(PermissionError):
            self.gateway.retrieve(
                "atlas-agent",
                "memory-001",
                operation_id="op-denied",
            )


if __name__ == "__main__":
    unittest.main()
