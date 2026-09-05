from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AgentStatus(StrEnum):
    CREATED = "created"
    VALIDATED = "validated"
    READY = "ready"
    RUNNING = "running"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class AgentIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: AgentStatus
