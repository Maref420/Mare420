"""Execution Engine models — Contract v0.1.

These models define the data contracts for the Agent Runtime Execution Engine.
They follow the same strict conventions used by the Agent Control Plane
(Scheduler, Identity, Audit): frozen, extra=forbid, explicit validation.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatus(StrEnum):
    """Status of an execution attempt inside the Runtime."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionRequest(BaseModel):
    """Request to execute a task that has already been admitted by the Scheduler.

    Pre-condition (enforced by caller / Scheduler):
        The corresponding AgentTask must already be in TaskStatus.RUNNING
        (i.e. Scheduler.start() has already succeeded).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    resource_units: int = Field(ge=1)


class ExecutionResult(BaseModel):
    """Outcome of an execution attempt.

    The Execution Engine produces this result. The caller (or the Engine itself)
    is responsible for translating a successful/failed result into
    Scheduler.complete() or Scheduler.fail().
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    status: ExecutionStatus
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
