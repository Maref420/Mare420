# MODULE: atlas-market-analyst
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: Models for unified market analysis output.
# POLICY: Frozen models. source_uri mandatory per ADR-006.
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AnalystDecision(str, Enum):
    STRONG_BUY_SIGNAL = "strong_buy_signal"
    BUY_SIGNAL = "buy_signal"
    HOLD = "hold"
    SELL_SIGNAL = "sell_signal"
    INVESTIGATE = "investigate"
    IGNORE = "ignore"


class MarketAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(..., min_length=1)
    decision: AnalystDecision
    confidence: float = Field(..., ge=0.0, le=1.0)
    aqs_score: int = Field(..., ge=0, le=100)
    spoofing_detected: bool
    arbitrage_profitable: bool
    net_arb_weight: float = Field(default=0.0)
    exchange_count: int = Field(..., ge=1)
    reasoning: str = Field(..., min_length=1, max_length=500)
    trace_id: str = Field(..., min_length=1)
    timestamp_ns: int = Field(..., gt=0)
    source_uri: str = Field(
        default="python-market-analyst://v1",
        description="Mandatory per ADR-006",
    )
