import unittest

from intelligence.agent_control_plane.identity.models import (
    AgentIdentity,
    AgentStatus,
)
from intelligence.agent_control_plane.lifecycle.engine import AgentLifecycleEngine
from intelligence.agent_control_plane.registry.registry import AgentRegistry


class TestAgentLifecycleEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AgentRegistry()
        self.registry.register(
            AgentIdentity(
                agent_id="agent-lifecycle-001",
                version="v0.1",
                status=AgentStatus.VALIDATED,
            )
        )
        self.lifecycle = AgentLifecycleEngine(self.registry)

    def test_startup_reaches_running(self) -> None:
        identity = self.lifecycle.startup("agent-lifecycle-001")

        self.assertEqual(identity.status, AgentStatus.RUNNING)
        registered = self.registry.get("agent-lifecycle-001")
        self.assertIsNotNone(registered)
        assert registered is not None
        self.assertEqual(registered.status, AgentStatus.RUNNING)

    def test_suspend_and_resume(self) -> None:
        self.lifecycle.startup("agent-lifecycle-001")

        suspended = self.lifecycle.suspend("agent-lifecycle-001")
        self.assertEqual(suspended.status, AgentStatus.SUSPENDED)

        resumed = self.lifecycle.resume("agent-lifecycle-001")
        self.assertEqual(resumed.status, AgentStatus.READY)

    def test_shutdown_is_controlled(self) -> None:
        self.lifecycle.startup("agent-lifecycle-001")

        terminated = self.lifecycle.shutdown("agent-lifecycle-001")

        self.assertEqual(terminated.status, AgentStatus.TERMINATED)

    def test_invalid_transition_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.lifecycle.shutdown("agent-lifecycle-001")

    def test_terminated_agent_cannot_restart(self) -> None:
        self.lifecycle.startup("agent-lifecycle-001")
        self.lifecycle.shutdown("agent-lifecycle-001")

        with self.assertRaises(ValueError):
            self.lifecycle.startup("agent-lifecycle-001")

    def test_unknown_agent_is_rejected(self) -> None:
        with self.assertRaises(PermissionError):
            self.lifecycle.startup("unknown-agent")


if __name__ == "__main__":
    unittest.main()
