"""Agent Runtime Execution Engine — Contract v0.1.

Scheduler owns admission, lifecycle, resources, and task status
transitions. This engine executes an already-started (RUNNING) task
and then requests Scheduler.complete() / Scheduler.fail().
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from intelligence.agent_control_plane.scheduler.engine import AgentScheduler
from intelligence.agent_control_plane.scheduler.models import AgentTask, TaskStatus
from intelligence.agent_runtime.execution.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)

ExecutionBehavior = Callable[[ExecutionRequest], Any]


class ExecutionRejectedError(ValueError):
    """Task was not eligible for execution. Scheduler status is unchanged."""


class AgentExecutionEngine:
    """Execute a Scheduler-started task. Does not call Scheduler.start()."""

    def __init__(
        self,
        scheduler: AgentScheduler,
        behavior: ExecutionBehavior,
    ) -> None:
        self._scheduler = scheduler
        self._behavior = behavior

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        task = self._require_running_task(request)

        try:
            output = self._behavior(request)
        except Exception as exc:  # noqa: BLE001 - any behavior error is a controlled execution failure
            return self._fail(task, exc)

        return self._complete(task, output)

    def _require_running_task(self, request: ExecutionRequest) -> AgentTask:
        task = self._scheduler.get(request.task_id)
        if task is None:
            raise ExecutionRejectedError("Unknown task.")
        if task.agent_id != request.agent_id:
            raise ExecutionRejectedError("Task agent_id does not match request.")
        if task.status is not TaskStatus.RUNNING:
            raise ExecutionRejectedError(
                "Only running tasks may be executed. "
                "Scheduler.start() must succeed before execute()."
            )
        if task.resource_units != request.resource_units:
            raise ExecutionRejectedError(
                "Request resource_units does not match the admitted task."
            )
        return task

    def _complete(self, task: AgentTask, output: Any) -> ExecutionResult:
        finished = self._scheduler.complete(task.task_id)
        return ExecutionResult(
            task_id=finished.task_id,
            agent_id=finished.agent_id,
            status=ExecutionStatus.COMPLETED,
            error=None,
            metadata={"output": output},
        )

    def _fail(self, task: AgentTask, exc: Exception) -> ExecutionResult:
        finished = self._scheduler.fail(task.task_id)
        return ExecutionResult(
            task_id=finished.task_id,
            agent_id=finished.agent_id,
            status=ExecutionStatus.FAILED,
            error=f"{type(exc).__name__}: {exc}",
            metadata={"exception_type": type(exc).__name__},
        )
