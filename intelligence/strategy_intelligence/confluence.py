"""
Confluence Matrix — Combines multiple strategy signals into unified decision.

Governed by:
- SE-1: No Single Strategy Execution (minimum 2 must align)
- SE-3: Agent Cross-Validation incorporated
- SE-4: Regime-Dependent Weighting
- Rule 12: Minimal Blast Radius (additive only)
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from intelligence.strategy_intelligence.strategy_evaluator.models import (
    Direction,
    Regime,
    StrategySignalEventV1,
)

logger = logging.getLogger(__name__)


class ConfluenceResult(BaseModel):
    """
    Immutable result of confluence analysis across all 6 strategies.
    Governed by: extra="forbid" to maintain contract purity.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    regime: Regime
    direction: Direction
    confluence_score: float = Field(..., ge=0.0, le=1.0)
    aligned_strategy_count: int = Field(..., ge=0)
    total_strategy_count: int
    dominant_strategies: tuple[str, ...]
    is_actionable: bool = Field(
        ...,
        description="True if SE-1 satisfied (>=2 strategies align)",
    )
    long_weighted_confidence: float = Field(..., ge=0.0, le=1.0)
    short_weighted_confidence: float = Field(..., ge=0.0, le=1.0)
    details: dict[str, Any] | None = None


# Regime-dependent strategy weights per SE-4.
# Each row sums to 1.0. Weights reflect which strategies perform best
# in each market regime based on quantitative trading literature.
REGIME_WEIGHTS: dict[Regime, dict[str, float]] = {
    Regime.TRENDING: {
        "slippage_evaluator_v1": 0.10,
        "price_slip_evaluator_v1": 0.20,
        "smart_money_evaluator_v1": 0.25,
        "volume_evaluator_v1": 0.20,
        "ict_evaluator_v1": 0.20,
        "iceberg_evaluator_v1": 0.05,
    },
    Regime.RANGING: {
        "slippage_evaluator_v1": 0.15,
        "price_slip_evaluator_v1": 0.05,
        "smart_money_evaluator_v1": 0.15,
        "volume_evaluator_v1": 0.15,
        "ict_evaluator_v1": 0.10,
        "iceberg_evaluator_v1": 0.40,
    },
    Regime.VOLATILE: {
        "slippage_evaluator_v1": 0.20,
        "price_slip_evaluator_v1": 0.15,
        "smart_money_evaluator_v1": 0.25,
        "volume_evaluator_v1": 0.15,
        "ict_evaluator_v1": 0.10,
        "iceberg_evaluator_v1": 0.15,
    },
    Regime.CALM: {
        "slippage_evaluator_v1": 0.25,
        "price_slip_evaluator_v1": 0.05,
        "smart_money_evaluator_v1": 0.10,
        "volume_evaluator_v1": 0.20,
        "ict_evaluator_v1": 0.10,
        "iceberg_evaluator_v1": 0.30,
    },
}

# Minimum confidence threshold for a signal to be considered
MIN_CONFIDENCE_THRESHOLD = 0.4

# Minimum number of aligned strategies required per SE-1
MIN_ALIGNED_STRATEGIES = 2


class ConfluenceMatrix:
    """
    Evaluates confluence across all 6 strategy signals.
    Produces a single unified ConfluenceResult for the Superconscious Loop.
    """

    @staticmethod
    def evaluate(
        signals: list[StrategySignalEventV1],
        regime: Regime,
    ) -> ConfluenceResult:
        """
        Combine multiple strategy signals into a confluence assessment.

        Args:
            signals: List of StrategySignalEventV1 from active evaluators.
            regime: Current market regime for weight selection.

        Returns:
            Frozen ConfluenceResult with actionable flag.
        """
        if not signals:
            return ConfluenceMatrix._empty_result(regime)

        symbol = signals[0].signal.symbol
        weights = REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS[Regime.CALM])

        # Filter: Remove FLAT signals and low-confidence signals
        valid_signals = [
            s for s in signals
            if s.signal.direction != Direction.FLAT
            and s.signal.confidence >= MIN_CONFIDENCE_THRESHOLD
        ]

        if not valid_signals:
            return ConfluenceMatrix._empty_result(regime, symbol=symbol)

        # Calculate weighted confidence for LONG and SHORT
        long_score = 0.0
        short_score = 0.0
        long_strategies: list[str] = []
        short_strategies: list[str] = []

        for sig in valid_signals:
            strategy_name = sig.source_agent
            weight = weights.get(strategy_name, 0.1)  # Default weight if unknown
            weighted_conf = sig.signal.confidence * weight

            if sig.signal.direction == Direction.LONG:
                long_score += weighted_conf
                long_strategies.append(strategy_name)
            elif sig.signal.direction == Direction.SHORT:
                short_score += weighted_conf
                short_strategies.append(strategy_name)

        # Clamp scores to [0.0, 1.0]
        long_score = min(1.0, max(0.0, long_score))
        short_score = min(1.0, max(0.0, short_score))

        # Determine dominant direction
        if long_score > short_score:
            direction = Direction.LONG
            aligned_count = len(long_strategies)
            dominant = tuple(long_strategies)
            confluence = long_score
        elif short_score > long_score:
            direction = Direction.SHORT
            aligned_count = len(short_strategies)
            dominant = tuple(short_strategies)
            confluence = short_score
        else:
            direction = Direction.FLAT
            aligned_count = 0
            dominant = ()
            confluence = 0.0

        # SE-1: Minimum 2 strategies must align
        is_actionable = (
            aligned_count >= MIN_ALIGNED_STRATEGIES
            and direction != Direction.FLAT
            and confluence >= MIN_CONFIDENCE_THRESHOLD
        )

        result = ConfluenceResult(
            symbol=symbol,
            regime=regime,
            direction=direction,
            confluence_score=round(confluence, 4),
            aligned_strategy_count=aligned_count,
            total_strategy_count=len(signals),
            dominant_strategies=dominant,
            is_actionable=is_actionable,
            long_weighted_confidence=round(long_score, 4),
            short_weighted_confidence=round(short_score, 4),
            details={
                "long_strategies": long_strategies,
                "short_strategies": short_strategies,
                "filtered_count": len(signals) - len(valid_signals),
            },
        )

        logger.info(
            "CONFLUENCE_EVALUATED",
            extra={
                "symbol": symbol,
                "regime": regime.value,
                "direction": direction.value,
                "score": round(confluence, 4),
                "aligned": aligned_count,
                "actionable": is_actionable,
            },
        )

        return result

    @staticmethod
    def _empty_result(
        regime: Regime, symbol: str = "UNKNOWN"
    ) -> ConfluenceResult:
        """Return non-actionable empty result when no valid signals exist."""
        return ConfluenceResult(
            symbol=symbol,
            regime=regime,
            direction=Direction.FLAT,
            confluence_score=0.0,
            aligned_strategy_count=0,
            total_strategy_count=0,
            dominant_strategies=(),
            is_actionable=False,
            long_weighted_confidence=0.0,
            short_weighted_confidence=0.0,
        )
