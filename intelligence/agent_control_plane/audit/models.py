from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditEventType(StrEnum):
    MEMORY_RETRIEVE = "memory.retrieve"
    MEMORY_STORE = "memory.store"
    MEMORY_FORGET = "memory.forget"
    COMMUNICATION_SEND = "communication.send"


class AuditAction(StrEnum):
    REQUESTED = "requested"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditResult(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class AuditRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    contract_version: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    event_type: AuditEventType
    operation_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    timestamp: datetime
    action: AuditAction
    resource: str = Field(min_length=1)
    result: AuditResult
    metadata: dict[str, Any]
