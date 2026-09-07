# MODULE: atlas-pricing-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: ErrorEnvelope-compatible codes (VAL_, DEP_, BIZ_, INT_)
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AppError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class UsageStats(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_id: str = Field(..., min_length=1, max_length=64)
    frames_total: int = Field(..., ge=0)
    bytes_total: int = Field(..., ge=0)
    dropped_frames: int = Field(..., ge=0)
    last_frame_at: str = Field(..., min_length=1)


class PricingTier(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: Literal["free", "pro", "enterprise"]
    max_fps: int
    max_bytes_monthly: int
    price_usd: float = Field(..., ge=0.0)


class BillingDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_id: str
    tier: str
    usage_pct: float = Field(..., ge=0.0)
    overage: bool = False
    action: Literal["continue", "throttle", "suspend", "upgrade_prompt"]
    invoice_usd: float = Field(..., ge=0.0)
    trace_id: str
    agent_id: str = "pricing_agent"
    timestamp_ms: int = Field(..., gt=0)


class CustomerRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_id: str
    api_key: str
    tier: str
    registered_at: str
    source_uri: str = Field(..., min_length=1, description="Mandatory per ADR-006")
