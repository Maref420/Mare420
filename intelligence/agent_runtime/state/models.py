from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RuntimeState(StrEnum):
    INITIALIZED = "initialized"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    TERMINATED = "terminated"


class AgentRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1)
    state: RuntimeState
