import unittest

from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
from intelligence.agent_control_plane.audit.models import (
    AuditAction,
    AuditEventType,
    AuditResult,
)
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
        self.audit = InMemoryAuditSink()
        self.scheduler = AgentScheduler(
            self.registry,
            self.lifecycle,
            SchedulerResources(capacity=10, available=10),
            audit_sink=self.audit,
        )

    def test_submit_is_audited_without_task_payload(self) -> None:
        self.scheduler.submit(
            AgentTask(
                task_id="audit-task-001",
                agent_id="agent-001",
            )
        )

        events = self.audit.events()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, AuditEventType.SCHEDULER_TASK)
        self.assertEqual(events[0].action, AuditAction.REQUESTED)
        self.assertEqual(events[0].result, AuditResult.SUCCESS)
        self.assertEqual(events[0].operation_id, "audit-task-001")
        self.assertEqual(events[0].agent_id, "agent-001")
        self.assertEqual(events[0].resource, "audit-task-001")
        self.assertEqual(events[0].metadata, {})

    def test_non_queued_task_is_rejected_on_submit(self) -> None:
        with self.assertRaises(ValueError):
            self.scheduler.submit(
                AgentTask(
                    task_id="non-queued-001",
                    agent_id="agent-001",
                    status=TaskStatus.RUNNING,
                )
            )

    def test_start_is_audited(self) -> None:
        self.scheduler.submit(
            AgentTask(
                task_id="audit-start-001",
                agent_id="agent-001",
            )
        )
        self.audit.events()

        self.scheduler.start("audit-start-001")
        events = self.audit.events()

        self.assertEqual(len(events), 2)
        self.assertEqual(events[1].action, AuditAction.REQUESTED)
        self.assertEqual(events[1].result, AuditResult.SUCCESS)
        self.assertEqual(events[1].operation_id, "audit-start-001")

    def test_complete_is_audited(self) -> None:
        self.scheduler.submit(
            AgentTask(
                task_id="audit-complete-001",
                agent_id="agent-001",
            )
        )
        self.scheduler.start("audit-complete-001")

        self.scheduler.complete("audit-complete-001")
        events = self.audit.events()

        self.assertEqual(len(events), 3)
        self.assertEqual(events[2].action, AuditAction.COMPLETED)
        self.assertEqual(events[2].result, AuditResult.SUCCESS)

    def test_fail_is_audited(self) -> None:
        self.scheduler.submit(
            AgentTask(
                task_id="audit-fail-001",
                agent_id="agent-001",
            )
        )
        self.scheduler.start("audit-fail-001")

        self.scheduler.fail("audit-fail-001")
        events = self.audit.events()

        self.assertEqual(len(events), 3)
        self.assertEqual(events[2].action, AuditAction.FAILED)
        self.assertEqual(events[2].result, AuditResult.FAILURE)

    def test_cancel_is_audited(self) -> None:
        self.scheduler.submit(
            AgentTask(
                task_id="audit-cancel-001",
                agent_id="agent-001",
            )
        )
        self.scheduler.start("audit-cancel-001")

        self.scheduler.cancel("audit-cancel-001")
        events = self.audit.events()

        self.assertEqual(len(events), 3)
        self.assertEqual(events[2].action, AuditAction.COMPLETED)
        self.assertEqual(events[2].result, AuditResult.SUCCESS)

    def test_submit_duplicate_task_is_not_audited(self) -> None:
        task = AgentTask(
            task_id="duplicate-001",
            agent_id="agent-001",
        )
        self.scheduler.submit(task)

        with self.assertRaises(ValueError):
            self.scheduler.submit(task)

        events = self.audit.events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, AuditAction.REQUESTED)
        self.assertEqual(events[0].result, AuditResult.SUCCESS)

    def test_failed_task_releases_resources(self) -> None:
        task = AgentTask(
            task_id="resource-fail-001",
            agent_id="agent-001",
            resource_units=4,
        )
        self.scheduler.submit(task)

        self.scheduler.start(task.task_id)
        failed = self.scheduler.fail(task.task_id)

        self.assertEqual(failed.status, TaskStatus.FAILED)

        events = self.audit.events()
        self.assertEqual(len(events), 3)
        self.assertEqual(events[2].action, AuditAction.FAILED)
        self.assertEqual(events[2].result, AuditResult.FAILURE)

    def test_cancel_releases_resources(self) -> None:
        task = AgentTask(
            task_id="resource-cancel-001",
            agent_id="agent-001",
            resource_units=4,
        )
        self.scheduler.submit(task)

        self.scheduler.start(task.task_id)
        cancelled = self.scheduler.cancel(task.task_id)

        self.assertEqual(cancelled.status, TaskStatus.CANCELLED)

        events = self.audit.events()
        self.assertEqual(len(events), 3)
        self.assertEqual(events[2].action, AuditAction.COMPLETED)
        self.assertEqual(events[2].result, AuditResult.SUCCESS)

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
