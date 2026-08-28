import unittest

from intelligence.agent_runtime.state.engine import (
    AgentRuntimeStateManager,
    InvalidRuntimeStateTransition,
)
from intelligence.agent_runtime.state.models import RuntimeState


class TestAgentRuntimeStateManager(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = AgentRuntimeStateManager()

    def test_initialize(self) -> None:
        state = self.manager.initialize("agent-001")

        self.assertEqual(state.agent_id, "agent-001")
        self.assertEqual(state.state, RuntimeState.INITIALIZED)

    def test_valid_transition_path(self) -> None:
        self.manager.initialize("agent-001")

        self.assertEqual(
            self.manager.transition(
                "agent-001",
                RuntimeState.READY,
            ).state,
            RuntimeState.READY,
        )
        self.assertEqual(
            self.manager.transition(
                "agent-001",
                RuntimeState.RUNNING,
            ).state,
            RuntimeState.RUNNING,
        )
        self.assertEqual(
            self.manager.transition(
                "agent-001",
                RuntimeState.PAUSED,
            ).state,
            RuntimeState.PAUSED,
        )
        self.assertEqual(
            self.manager.transition(
                "agent-001",
                RuntimeState.RUNNING,
            ).state,
            RuntimeState.RUNNING,
        )

    def test_failed_can_only_terminate(self) -> None:
        self.manager.initialize("agent-001")
        self.manager.transition("agent-001", RuntimeState.READY)
        self.manager.transition("agent-001", RuntimeState.RUNNING)
        self.manager.transition("agent-001", RuntimeState.FAILED)

        state = self.manager.transition(
            "agent-001",
            RuntimeState.TERMINATED,
        )

        self.assertEqual(state.state, RuntimeState.TERMINATED)

    def test_invalid_transition_is_rejected(self) -> None:
        self.manager.initialize("agent-001")

        with self.assertRaises(InvalidRuntimeStateTransition):
            self.manager.transition(
                "agent-001",
                RuntimeState.RUNNING,
            )

    def test_terminated_is_terminal(self) -> None:
        self.manager.initialize("agent-001")
        self.manager.transition("agent-001", RuntimeState.READY)
        self.manager.transition("agent-001", RuntimeState.RUNNING)
        self.manager.transition("agent-001", RuntimeState.TERMINATED)

        with self.assertRaises(InvalidRuntimeStateTransition):
            self.manager.transition(
                "agent-001",
                RuntimeState.RUNNING,
            )

    def test_duplicate_initialization_is_rejected(self) -> None:
        self.manager.initialize("agent-001")

        with self.assertRaises(ValueError):
            self.manager.initialize("agent-001")

    def test_unknown_agent_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            self.manager.transition(
                "missing-agent",
                RuntimeState.READY,
            )


if __name__ == "__main__":
    unittest.main()
