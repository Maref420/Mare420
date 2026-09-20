"""
Abstract Base Strategy Evaluator.
All 6 smart strategies must implement this interface.

Governed by:
- SE-5: Zero Mutation (new file, additive only)
- Rule 12: Minimal Blast Radius
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from intelligence.strategy_intelligence.strategy_evaluator.models import (
    Direction,
    Regime,
    SignalPayload,
    StrategySignalEventV1,
)


class MarketSnapshot(BaseModel):
    """
    Standardized market data input for all evaluators.
    Populated from Go Ingestion service via NATS.
    """
    model_config = ConfigDict(extra="allow", frozen=True)

    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    last_price: float
    volume_24h: float
    trades: list[dict[str, Any]] = Field(default_factory=list)
    orderbook_bids: list[tuple[float, float]] = Field(default_factory=list)
    orderbook_asks: list[tuple[float, float]] = Field(default_factory=list)
    funding_rate: float | None = None
    open_interest: float | None = None


class AgentContext(BaseModel):
    """
    Contextual signals from sensory agents.
    Not all evaluators use all agent signals.
    """
    model_config = ConfigDict(extra="allow", frozen=True)

    news_sentiment: float = 0.0
    social_hype: float = 0.0
    wallet_whale_flow: float = 0.0
    wallet_exchange_inflow: float = 0.0


class BaseStrategyEvaluator(ABC):
    """
    Abstract base class for all strategy evaluators.

    Each concrete evaluator must implement:
    - strategy_name: Unique identifier
    - evaluate(): Core logic producing a StrategySignalEventV1
    """

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Unique strategy identifier."""
        ...

    @abstractmethod
    def evaluate(
        self,
        market: MarketSnapshot,
        agents: AgentContext,
        regime: Regime,
    ) -> StrategySignalEventV1 | None:
        """
        Evaluate market conditions and produce a signal.

        Returns None if strategy has no signal (no trade opportunity).
        Returns StrategySignalEventV1 if signal detected.

        Governed by:
        - SE-3: No single strategy execution (caller enforces confluence)
        - Schema compliance: output must match strategy-signal-event-v1
        """
        ...

    def _build_signal(
        self,
        symbol: str,
        direction: Direction,
        confidence: float,
        regime: Regime,
        parameters: dict[str, Any] | None = None,
    ) -> StrategySignalEventV1:
        """
        Helper to construct schema-compliant signal events.
        All evaluators should use this to ensure consistency.
        """
        clamped_confidence = max(0.0, min(1.0, confidence))

        return StrategySignalEventV1(
            version="1.0.0",
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC),
            source_agent=self.strategy_name,
            signal=SignalPayload(
                symbol=symbol,
                direction=direction,
                confidence=clamped_confidence,
                regime=regime,
                parameters=parameters,
            ),
        )
