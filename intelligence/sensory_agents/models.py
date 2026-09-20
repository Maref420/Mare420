"""
Sensory Agents — Shared Models for News, Social, and Wallet agents.

Governed by:
- SE-4: Agent Cross-Validation
- Rule 10: Immutable Contracts (frozen Pydantic models)
- Rule 12: Minimal Blast Radius (additive only)
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentType(StrEnum):
    """Classification of sensory agent types."""
    NEWS = "news_agent"
    SOCIAL = "social_agent"
    WALLET = "wallet_agent"


class SentimentLevel(StrEnum):
    """Standardized sentiment classification."""
    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"


class AgentSignal(BaseModel):
    """
    Standardized output from all sensory agents.
    Consumed by Strategy Evaluators via AgentContext mapping.
    Frozen to prevent post-creation mutation per Rule 10.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_type: AgentType
    timestamp_utc: datetime
    symbol: str = Field(..., min_length=2, max_length=20)
    sentiment: SentimentLevel
    score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Normalized score: -1.0=max bearish, 1.0=max bullish",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier of the data source (article URL, tweet ID, tx hash)",
    )
    metadata: dict[str, Any] | None = None

    def to_context_value(self) -> float:
        """
        Convert signal to a normalized float for AgentContext.
        Maps sentiment score weighted by confidence to [-1.0, 1.0].
        """
        return self.score * self.confidence
