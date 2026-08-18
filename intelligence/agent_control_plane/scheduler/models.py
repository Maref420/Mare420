from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    priority: TaskPriority = TaskPriority.NORMAL
    resource_units: int = Field(default=1, ge=1)
    status: TaskStatus = TaskStatus.QUEUED


class SchedulerResources(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capacity: int = Field(ge=1)
    available: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_available_capacity(self) -> "SchedulerResources":
        if self.available > self.capacity:
            raise ValueError(
                "available resources cannot exceed scheduler capacity."
            )
        return self
