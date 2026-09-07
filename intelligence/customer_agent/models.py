# MODULE: atlas-customer-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: ErrorEnvelope-compatible codes (VAL_, BIZ_, INT_)
# SECURITY: api_key MUST be masked in all responses and logs.
from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AppError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_id: str = Field(..., min_length=1, max_length=64)
    api_key: str = Field(..., min_length=16, max_length=128)
    tier: str = Field(..., min_length=1, max_length=32)
    source_uri: str = Field(..., min_length=1, description="Mandatory per ADR-006")


class RegistrationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_id: str
    status: Literal["registered", "rejected"]
    tier: str
    api_key_prefix: str
    message: str
    timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    agent_id: str = "customer_agent"


class TierChangeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    new_tier: str = Field(..., min_length=1, max_length=32)
    reason: str = Field(..., min_length=1, max_length=256)
    source_uri: str = Field(..., min_length=1, description="Mandatory per ADR-006")


class TierChangeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_id: str
    old_tier: str
    new_tier: str
    action: str
    invoice_usd: float
    timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))


class CustomerRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_id: str
    api_key: str
    tier: str
    registered_at: str
    status: Literal["active", "suspended", "deleted"]
    source_uri: str


def mask_api_key(api_key: str) -> str:
    if len(api_key) < 9:
        return api_key[:3] + "..." + api_key[-3:]
    return api_key[:6] + "..." + api_key[-3:]
