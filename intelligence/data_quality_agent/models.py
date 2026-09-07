# MODULE: atlas-data-quality-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: ErrorEnvelope-compatible codes (VAL_, BIZ_, INT_)
# POLICY: No floats in price fields. Frozen models. source_uri mandatory per ADR-006.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AppError(Exception):
    """Domain exception with ErrorEnvelope-compatible code."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class SpreadSignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(..., min_length=1, max_length=32)
    buy_exchange: str = Field(..., min_length=1, max_length=64)
    sell_exchange: str = Field(..., min_length=1, max_length=64)
    buy_price_scaled: int = Field(..., ge=0)
    sell_price_scaled: int = Field(..., ge=0)
    spread_bps: int = Field(..., ge=0)
    timestamp_ns: int = Field(..., gt=0)
    source_uri: str = Field(..., min_length=1, description="Mandatory provenance per ADR-006")


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(..., min_length=1, max_length=32)
    source_count: int = Field(..., ge=0)
    median_price_scaled: int = Field(..., ge=0)
    spread_bps: int = Field(..., ge=0)
    anomalous_exchanges: list[str] = Field(default_factory=list)
    is_valid: bool
    timestamp_ms: int = Field(..., gt=0)


class AnomalyAlert(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    severity: Literal["warning", "critical"]
    symbol: str
    exchange: str
    issue: str
    details: str
    trace_id: str
    agent_id: str = "data_quality_agent"
    timestamp_ms: int = Field(..., gt=0)
