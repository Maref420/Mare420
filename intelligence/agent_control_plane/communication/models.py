from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MessageType(StrEnum):
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    COMMAND = "command"


class MessageStatus(StrEnum):
    CREATED = "created"
    DELIVERED = "delivered"
    REJECTED = "rejected"


class AgentMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: str = Field(min_length=1)
    sender_id: str = Field(min_length=1)
    recipient_id: str = Field(min_length=1)
    message_type: MessageType
    payload: dict[str, object]
    status: MessageStatus = MessageStatus.CREATED


class CommunicationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allow_agent_to_agent: bool = True
    allow_agent_to_system: bool = False
    allow_system_to_agent: bool = True
