"""
Strategy Signal Event V1 — Pydantic Contract Model.
Exact mapping of contracts/schemas/strategy/strategy-signal-event-v1.schema.json.

Governed by:
- additionalProperties: false (Schema Rule)
- ATLAS Protocol Rule 10 (Immutable Contracts)
- SE-2: Schema Compliance

WARNING: Do NOT add extra fields. Go Broker will reject any message
with fields not defined in the JSON Schema.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Direction(StrEnum):
    """Allowed signal directions per schema."""
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class Regime(StrEnum):
    """Allowed market regimes per schema."""
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    CALM = "CALM"


class SignalPayload(BaseModel):
    """Inner signal object per schema definition."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(..., min_length=2, max_length=20)
    direction: Direction
    confidence: float = Field(..., ge=0.0, le=1.0)
    regime: Regime
    parameters: dict[str, Any] | None = None

    @field_validator("symbol")
    @classmethod
    def validate_symbol_pattern(cls, v: str) -> str:
        import re
        if not re.match(r"^[A-Z0-9]{2,20}$", v):
            raise ValueError(f"symbol must match ^[A-Z0-9]{{2,20}}$, got {v}")
        return v


class StrategySignalEventV1(BaseModel):
    """
    Top-level event envelope matching strategy-signal-event-v1.schema.json.
    Frozen to prevent post-creation mutation.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(default="1.0.0")
    event_id: str = Field(..., min_length=1)
    timestamp_utc: datetime
    source_agent: str = Field(..., min_length=1)
    signal: SignalPayload
    trace_id: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != "1.0.0":
            raise ValueError(f"version must be 1.0.0, got {v}")
        return v
