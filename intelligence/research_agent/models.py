# MODULE: atlas-research-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: ErrorEnvelope-compatible codes (VAL_, DEP_, INT_)
# POLICY: Frozen models. source_uri mandatory per ADR-006.
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AppError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class ForensicsSignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(..., min_length=1, max_length=32)
    raw_spread_bps: int = Field(..., ge=0)
    aqs_score: int = Field(..., ge=0, le=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    orderbook_imbalance: float = Field(..., ge=-1.0, le=1.0)
    vpin_toxicity: float = Field(..., ge=0.0, le=1.0)
    spoofing_detected: bool
    trace_id: str = Field(..., min_length=1)
    timestamp_ns: int = Field(..., gt=0)
    source_uri: str = Field(..., min_length=1, description="Mandatory per ADR-006")


class ResearchDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    action: Literal["investigate", "archive", "alert", "ignore"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    memory_refs: list[str]
    trace_id: str = Field(..., min_length=1)
    agent_id: str = "research_agent"
    timestamp_ms: int = Field(..., gt=0)


class PatternRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pattern_id: str
    symbol: str
    conditions: dict[str, Any]
    win_rate: float = Field(..., ge=0.0, le=1.0)
    sample_count: int = Field(..., ge=0)
    last_seen_ms: int = Field(..., gt=0)
    source_uri: str = Field(..., min_length=1, description="Mandatory per ADR-006")


class ExperimentResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_id: str
    pattern_id: str
    outcome: Literal["win", "loss", "draw"]
    pnl_scaled: int
    details: str
    timestamp_ms: int = Field(..., gt=0)
