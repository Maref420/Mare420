import unittest

from intelligence.agent_control_plane.identity.models import (
    AgentIdentity,
    AgentStatus,
)
from intelligence.agent_control_plane.lifecycle.engine import AgentLifecycleEngine
from intelligence.agent_control_plane.registry.registry import AgentRegistry
from intelligence.agent_control_plane.scheduler.engine import AgentScheduler
from intelligence.agent_control_plane.scheduler.models import (
    AgentTask,
    SchedulerResources,
    TaskPriority,
    TaskStatus,
)


class TestAgentScheduler(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AgentRegistry()
        self.registry.register(
            AgentIdentity(
                agent_id="agent-001",
                version="v0.1",
                status=AgentStatus.VALIDATED,
            )
        )
        self.lifecycle = AgentLifecycleEngine(self.registry)
        self.lifecycle.startup("agent-001")
        self.scheduler = AgentScheduler(
            self.registry,
            self.lifecycle,
            SchedulerResources(capacity=10, available=10),
        )

    def test_priority_ordering(self) -> None:
        self.scheduler.submit(
            AgentTask(
                task_id="low",
                agent_id="agent-001",
                priority=TaskPriority.LOW,
            )
        )
        self.scheduler.submit(
            AgentTask(
                task_id="critical",
                agent_id="agent-001",
                priority=TaskPriority.CRITICAL,
            )
        )

        task = self.scheduler.next_task()

        self.assertIsNotNone(task)
        self.assertEqual(task.task_id, "critical")

    def test_task_lifecycle(self) -> None:
        self.scheduler.submit(
            AgentTask(
                task_id="task-001",
                agent_id="agent-001",
            )
        )

        running = self.scheduler.start("task-001")
        self.assertEqual(running.status, TaskStatus.RUNNING)

        completed = self.scheduler.complete("task-001")
        self.assertEqual(completed.status, TaskStatus.COMPLETED)

    def test_unknown_agent_rejected(self) -> None:
        with self.assertRaises(PermissionError):
            self.scheduler.submit(
                AgentTask(
                    task_id="task-002",
                    agent_id="unknown-agent",
                )
            )

    def test_resource_limit_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            self.scheduler.submit(
                AgentTask(
                    task_id="task-003",
                    agent_id="agent-001",
                    resource_units=11,
                )
            )

    def test_resource_invariant_rejects_available_above_capacity(self) -> None:
        with self.assertRaises(ValueError):
            SchedulerResources(capacity=10, available=11)

    def test_queued_task_rechecks_agent_lifecycle_before_start(self) -> None:
        self.scheduler.submit(
            AgentTask(
                task_id="task-lifecycle-001",
                agent_id="agent-001",
            )
        )

        self.lifecycle.shutdown("agent-001")

        with self.assertRaises(PermissionError):
            self.scheduler.start("task-lifecycle-001")


if __name__ == "__main__":
    unittest.main()
