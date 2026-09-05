import unittest

from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
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
    TaskStatus,
)
from intelligence.agent_runtime.execution.engine import (
    AgentExecutionEngine,
    ExecutionRejectedError,
)
from intelligence.agent_runtime.execution.models import (
    ExecutionRequest,
    ExecutionStatus,
)


class TestAgentExecutionEngine(unittest.TestCase):
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

    def _require_task(self, task_id: str) -> AgentTask:
        task = self.scheduler.get(task_id)
        if task is None:
            self.fail(f"Expected task {task_id} to exist.")
        return task

    def _admit_running(self, task_id: str, resource_units: int = 1) -> AgentTask:
        submitted = self.scheduler.submit(
            AgentTask(
                task_id=task_id,
                agent_id="agent-001",
                resource_units=resource_units,
            )
        )
        return self.scheduler.start(submitted.task_id)

    def test_successful_execution_completes_scheduler_task(self) -> None:
        task = self._admit_running("exec-success-001")
        engine = AgentExecutionEngine(
            self.scheduler,
            behavior=lambda request: {"ok": True, "task_id": request.task_id},
        )

        result = engine.execute(
            ExecutionRequest(
                task_id=task.task_id,
                agent_id=task.agent_id,
                resource_units=task.resource_units,
            )
        )

        self.assertEqual(result.status, ExecutionStatus.COMPLETED)
        self.assertIsNone(result.error)
        self.assertEqual(result.task_id, task.task_id)
        self.assertEqual(result.agent_id, "agent-001")
        self.assertEqual(result.metadata["output"]["ok"], True)
        finished = self._require_task(task.task_id)
        self.assertEqual(finished.status, TaskStatus.COMPLETED)

    def test_unknown_task_is_rejected_without_scheduler_finish(self) -> None:
        engine = AgentExecutionEngine(
            self.scheduler,
            behavior=lambda request: None,
        )

        with self.assertRaises(ExecutionRejectedError):
            engine.execute(
                ExecutionRequest(
                    task_id="missing-001",
                    agent_id="agent-001",
                    resource_units=1,
                )
            )

        self.assertIsNone(self.scheduler.get("missing-001"))

    def test_queued_task_is_rejected_and_stays_queued(self) -> None:
        queued = self.scheduler.submit(
            AgentTask(
                task_id="exec-queued-001",
                agent_id="agent-001",
            )
        )
        engine = AgentExecutionEngine(
            self.scheduler,
            behavior=lambda request: {"should_not_run": True},
        )

        with self.assertRaises(ExecutionRejectedError):
            engine.execute(
                ExecutionRequest(
                    task_id=queued.task_id,
                    agent_id=queued.agent_id,
                    resource_units=queued.resource_units,
                )
            )

        self.assertEqual(self._require_task(queued.task_id).status, TaskStatus.QUEUED)

    def test_execution_failure_fails_scheduler_task_and_preserves_cause(self) -> None:
        task = self._admit_running("exec-fail-001")

        def boom(_request: ExecutionRequest) -> None:
            raise RuntimeError("behavior exploded")

        engine = AgentExecutionEngine(self.scheduler, behavior=boom)
        result = engine.execute(
            ExecutionRequest(
                task_id=task.task_id,
                agent_id=task.agent_id,
                resource_units=task.resource_units,
            )
        )

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.error, "RuntimeError: behavior exploded")
        self.assertEqual(result.metadata["exception_type"], "RuntimeError")
        finished = self._require_task(task.task_id)
        self.assertEqual(finished.status, TaskStatus.FAILED)

    def test_agent_id_mismatch_is_rejected(self) -> None:
        task = self._admit_running("exec-mismatch-001")
        engine = AgentExecutionEngine(
            self.scheduler,
            behavior=lambda request: None,
        )

        with self.assertRaises(ExecutionRejectedError):
            engine.execute(
                ExecutionRequest(
                    task_id=task.task_id,
                    agent_id="other-agent",
                    resource_units=task.resource_units,
                )
            )

        self.assertEqual(self._require_task(task.task_id).status, TaskStatus.RUNNING)

    def test_resource_units_mismatch_is_rejected(self) -> None:
        task = self._admit_running("exec-resource-001", resource_units=3)
        engine = AgentExecutionEngine(
            self.scheduler,
            behavior=lambda request: None,
        )

        with self.assertRaises(ExecutionRejectedError):
            engine.execute(
                ExecutionRequest(
                    task_id=task.task_id,
                    agent_id=task.agent_id,
                    resource_units=1,
                )
            )

        self.assertEqual(self._require_task(task.task_id).status, TaskStatus.RUNNING)
