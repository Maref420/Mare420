from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Capability(StrEnum):
    MEMORY_RETRIEVE = "memory.retrieve"
    MEMORY_STORE = "memory.store"
    MEMORY_FORGET = "memory.forget"


class PermissionSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1)
    capabilities: frozenset[Capability]
