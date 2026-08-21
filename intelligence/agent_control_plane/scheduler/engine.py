from datetime import datetime, timezone
from typing import ClassVar
from uuid import uuid4

from intelligence.agent_control_plane.audit.interface import AuditSink
from intelligence.agent_control_plane.audit.models import (
    AuditAction,
    AuditEventType,
    AuditRecord,
    AuditResult,
)
from intelligence.agent_control_plane.identity.models import AgentStatus
from intelligence.agent_control_plane.lifecycle.engine import AgentLifecycleEngine
from intelligence.agent_control_plane.registry.registry import AgentRegistry
from intelligence.agent_control_plane.scheduler.models import (
    AgentTask,
    SchedulerResources,
    TaskPriority,
    TaskStatus,
)


class AgentScheduler:
    """Controlled scheduler for validated and lifecycle-authorized Agents."""

    _PRIORITY: ClassVar[dict[TaskPriority, int]] = {
        TaskPriority.CRITICAL: 0,
        TaskPriority.HIGH: 1,
        TaskPriority.NORMAL: 2,
        TaskPriority.LOW: 3,
    }

    def __init__(
        self,
        registry: AgentRegistry,
        lifecycle: AgentLifecycleEngine,
        resources: SchedulerResources,
        audit_sink: AuditSink,
    ) -> None:
        self._registry = registry
        self._lifecycle = lifecycle
        self._resources = resources
        self._audit_sink = audit_sink
        self._tasks: dict[str, AgentTask] = {}

    def submit(self, task: AgentTask) -> AgentTask:
        if task.task_id in self._tasks:
            self._audit_rejection(task)
            raise ValueError("Task is already registered.")
        if task.status is not TaskStatus.QUEUED:
            self._audit_rejection(task)
            raise ValueError("Only queued tasks may be submitted.")

        identity = self._registry.get(task.agent_id)
        if identity is None:
            self._audit_rejection(task)
            raise PermissionError("Unknown Agent.")

        if identity.status not in {
            AgentStatus.READY,
            AgentStatus.RUNNING,
        }:
            self._audit_rejection(task)
            raise PermissionError("Agent is not schedulable.")

        if task.resource_units > self._resources.capacity:
            self._audit_rejection(task)
            raise RuntimeError("Task exceeds scheduler capacity.")

        self._tasks[task.task_id] = task

        self._audit(
            action=AuditAction.REQUESTED,
            result=AuditResult.SUCCESS,
            task=task,
        )

        return task

    def next_task(self) -> AgentTask | None:
        queued = [
            task
            for task in self._tasks.values()
            if task.status is TaskStatus.QUEUED
        ]

        if not queued:
            return None

        return min(
            queued,
            key=lambda task: (
                self._PRIORITY[task.priority],
                task.task_id,
            ),
        )

    def start(self, task_id: str) -> AgentTask:
        task = self._get(task_id)

        if task.status is not TaskStatus.QUEUED:
            self._audit_rejection(task)
            raise ValueError("Only queued tasks may start.")

        identity = self._registry.get(task.agent_id)
        if identity is None:
            self._audit_rejection(task)
            raise PermissionError("Unknown Agent.")

        if identity.status not in {
            AgentStatus.READY,
            AgentStatus.RUNNING,
        }:
            self._audit_rejection(task)
            raise PermissionError("Agent is not schedulable.")

        if task.resource_units > self._resources.available:
            self._audit_rejection(task)
            raise RuntimeError("Insufficient scheduler resources.")

        new_available = self._resources.available - task.resource_units
        self._resources = self._resources.model_copy(
            update={"available": new_available}
        )

        updated = task.model_copy(update={"status": TaskStatus.RUNNING})
        self._tasks[task_id] = updated

        self._audit(
            action=AuditAction.REQUESTED,
            result=AuditResult.SUCCESS,
            task=updated,
        )

        return updated

    def complete(self, task_id: str) -> AgentTask:
        return self._finish(task_id, TaskStatus.COMPLETED)

    def fail(self, task_id: str) -> AgentTask:
        return self._finish(task_id, TaskStatus.FAILED)

    def cancel(self, task_id: str) -> AgentTask:
        return self._finish(task_id, TaskStatus.CANCELLED)

    def _audit_rejection(self, task: AgentTask) -> None:
        self._audit(
            action=AuditAction.FAILED,
            result=AuditResult.FAILURE,
            task=task,
        )

    def _audit(
        self,
        *,
        action: AuditAction,
        result: AuditResult,
        task: AgentTask,
    ) -> None:
        self._audit_sink.record(
            AuditRecord(
                contract_version="1.0",
                event_id=str(uuid4()),
                event_type=AuditEventType.SCHEDULER_TASK,
                operation_id=task.task_id,
                agent_id=task.agent_id,
                timestamp=datetime.now(timezone.utc),
                action=action,
                resource=task.task_id,
                result=result,
                metadata={},
            )
        )

    def get(self, task_id: str) -> AgentTask | None:
        if not task_id:
            raise ValueError("task_id must not be empty.")
        return self._tasks.get(task_id)

    def _get(self, task_id: str) -> AgentTask:
        task = self.get(task_id)
        if task is None:
            raise KeyError("Unknown task.")
        return task

    def _finish(
        self,
        task_id: str,
        status: TaskStatus,
    ) -> AgentTask:
        task = self._get(task_id)

        if task.status is not TaskStatus.RUNNING:
            self._audit_rejection(task)
            raise ValueError("Only running tasks may finish.")

        new_available = self._resources.available + task.resource_units
        if new_available > self._resources.capacity:
            raise RuntimeError("Scheduler resource accounting overflow.")

        self._resources = self._resources.model_copy(
            update={"available": new_available}
        )

        updated = task.model_copy(update={"status": status})
        self._tasks[task_id] = updated

        if status is TaskStatus.FAILED:
            self._audit(
                action=AuditAction.FAILED,
                result=AuditResult.FAILURE,
                task=updated,
            )
        else:
            self._audit(
                action=AuditAction.COMPLETED,
                result=AuditResult.SUCCESS,
                task=updated,
            )

        return updated
