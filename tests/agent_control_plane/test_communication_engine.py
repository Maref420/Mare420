import unittest

from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
from intelligence.agent_control_plane.audit.models import (
    AuditAction,
    AuditEventType,
    AuditResult,
)
from intelligence.agent_control_plane.communication.engine import (
    AgentCommunicationEngine,
)
from intelligence.agent_control_plane.communication.models import (
    AgentMessage,
    CommunicationPolicy,
    MessageStatus,
    MessageType,
)
from intelligence.agent_control_plane.identity.models import (
    AgentIdentity,
    AgentStatus,
)
from intelligence.agent_control_plane.registry.registry import AgentRegistry


class TestAgentCommunicationEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AgentRegistry()

        self.registry.register(
            AgentIdentity(
                agent_id="agent-001",
                version="v0.1",
                status=AgentStatus.VALIDATED,
            )
        )
        self.registry.register(
            AgentIdentity(
                agent_id="agent-002",
                version="v0.1",
                status=AgentStatus.VALIDATED,
            )
        )

        self.registry.replace(
            AgentIdentity(
                agent_id="agent-001",
                version="v0.1",
                status=AgentStatus.READY,
            )
        )
        self.registry.replace(
            AgentIdentity(
                agent_id="agent-002",
                version="v0.1",
                status=AgentStatus.READY,
            )
        )

        self.audit = InMemoryAuditSink()

        self.engine = AgentCommunicationEngine(
            self.registry,
            CommunicationPolicy(),
            self.audit,
        )

    def _message(
        self,
        message_id: str = "message-001",
        recipient_id: str = "agent-002",
    ) -> AgentMessage:
        return AgentMessage(
            message_id=message_id,
            sender_id="agent-001",
            recipient_id=recipient_id,
            message_type=MessageType.REQUEST,
            payload={"operation": "test"},
        )

    def test_agent_to_agent_delivery(self) -> None:
        delivered = self.engine.send(self._message())

        self.assertEqual(delivered.status, MessageStatus.DELIVERED)
        self.assertEqual(
            self.engine.get("message-001"),
            delivered,
        )

    def test_successful_delivery_is_audited(self) -> None:
        delivered = self.engine.send(self._message())

        events = self.audit.events()

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_type, AuditEventType.COMMUNICATION_SEND)
        self.assertEqual(events[0].action, AuditAction.REQUESTED)
        self.assertEqual(events[0].result, AuditResult.SUCCESS)
        self.assertEqual(events[1].event_type, AuditEventType.COMMUNICATION_SEND)
        self.assertEqual(events[1].action, AuditAction.COMPLETED)
        self.assertEqual(events[1].result, AuditResult.SUCCESS)
        self.assertEqual(events[1].resource, delivered.recipient_id)

    def test_rejected_delivery_is_audited(self) -> None:
        message = self._message(
            message_id="message-audit-rejected",
            recipient_id="system",
        )

        with self.assertRaises(PermissionError):
            self.engine.send(message)

        events = self.audit.events()

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].action, AuditAction.REQUESTED)
        self.assertEqual(events[1].action, AuditAction.FAILED)
        self.assertEqual(events[1].result, AuditResult.FAILURE)

    def test_unknown_sender_rejected(self) -> None:
        message = AgentMessage(
            message_id="message-002",
            sender_id="unknown-agent",
            recipient_id="agent-002",
            message_type=MessageType.REQUEST,
            payload={},
        )

        with self.assertRaises(PermissionError):
            self.engine.send(message)

    def test_suspended_recipient_rejected(self) -> None:
        self.registry.replace(
            AgentIdentity(
                agent_id="agent-002",
                version="v0.1",
                status=AgentStatus.SUSPENDED,
            )
        )

        with self.assertRaises(PermissionError):
            self.engine.send(
                AgentMessage(
                    message_id="message-suspended-recipient",
                    sender_id="agent-001",
                    recipient_id="agent-002",
                    message_type=MessageType.REQUEST,
                    payload={"action": "test"},
                )
            )

    def test_non_authorized_sender_rejected(self) -> None:
        self.registry.register(
            AgentIdentity(
                agent_id="agent-003",
                version="v0.1",
                status=AgentStatus.VALIDATED,
            )
        )

        message = AgentMessage(
            message_id="message-003",
            sender_id="agent-003",
            recipient_id="agent-002",
            message_type=MessageType.REQUEST,
            payload={},
        )

        with self.assertRaises(PermissionError):
            self.engine.send(message)

    def test_disabled_agent_to_agent_communication_rejected(self) -> None:
        engine = AgentCommunicationEngine(
            self.registry,
            CommunicationPolicy(allow_agent_to_agent=False),
            self.audit,
        )

        with self.assertRaises(PermissionError):
            engine.send(self._message())

    def test_agent_to_system_communication_rejected_by_default(self) -> None:
        message = self._message(
            message_id="message-004",
            recipient_id="system",
        )

        with self.assertRaises(PermissionError):
            self.engine.send(message)

    def test_agent_to_system_communication_can_be_enabled(self) -> None:
        engine = AgentCommunicationEngine(
            self.registry,
            CommunicationPolicy(allow_agent_to_system=True),
            self.audit,
        )

        delivered = engine.send(
            self._message(
                message_id="message-005",
                recipient_id="system",
            )
        )

        self.assertEqual(delivered.status, MessageStatus.DELIVERED)

    def test_unavailable_recipient_rejected(self) -> None:
        self.registry.register(
            AgentIdentity(
                agent_id="agent-003",
                version="v0.1",
                status=AgentStatus.VALIDATED,
            )
        )

        with self.assertRaises(PermissionError):
            self.engine.send(
                self._message(
                    message_id="message-006",
                    recipient_id="agent-003",
                )
            )

    def test_duplicate_message_rejected(self) -> None:
        self.engine.send(self._message())

        with self.assertRaises(ValueError):
            self.engine.send(self._message())

    def test_empty_message_id_rejected_on_lookup(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.get("")

    def test_unknown_message_rejected(self) -> None:
        with self.assertRaises(KeyError):
            self.engine.reject("unknown-message")

    def test_delivered_message_cannot_be_rejected(self) -> None:
        self.engine.send(self._message())

        with self.assertRaises(ValueError):
            self.engine.reject("message-001")


if __name__ == "__main__":
    unittest.main()
