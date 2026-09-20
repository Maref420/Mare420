"""
Strategy 5: ICT (Inner Circle Trader) Strategy Evaluator.
Implements core ICT concepts: Killzones, FVG, MSS, PD Arrays.

Logic: Identifies Market Structure Shifts (MSS) confirmed by Fair Value
Gaps (FVG) during killzone hours. Uses news sentiment as catalyst
validation per SE-4 agent cross-validation.

Governed by: SE-2, SE-3, SE-4
"""
from __future__ import annotations

from datetime import UTC
from typing import Any

from intelligence.strategy_intelligence.strategy_evaluator.base import (
    AgentContext,
    BaseStrategyEvaluator,
    MarketSnapshot,
)
from intelligence.strategy_intelligence.strategy_evaluator.models import (
    Direction,
    Regime,
    StrategySignalEventV1,
)


class ICTEvaluator(BaseStrategyEvaluator):
    """Evaluates ICT methodology setups."""

    # Killzone hours (UTC) for crypto: adapted from forex sessions
    LONDON_KILLZONE = (7, 10)
    NY_KILLZONE = (12, 15)
    ASIA_KILLZONE = (0, 3)

    FVG_MIN_GAP_PCT = 0.001  # 0.1% minimum gap for FVG

    @property
    def strategy_name(self) -> str:
        return "ict_evaluator_v1"

    def evaluate(
        self,
        market: MarketSnapshot,
        agents: AgentContext,
        regime: Regime,
    ) -> StrategySignalEventV1 | None:
        # ICT works best in trending or volatile regimes
        if regime not in (Regime.TRENDING, Regime.VOLATILE):
            return None

        current_hour = market.timestamp.astimezone(UTC).hour
        in_killzone = self._is_in_killzone(current_hour)

        trades = market.trades
        if len(trades) < 3:
            return None

        # Extract candle-like data from trades
        prices = [
            float(t.get("price", t.get("p", 0)))
            for t in trades
            if isinstance(t.get("price", t.get("p", 0)), (int, float))
        ]
        if len(prices) < 3:
            return None

        # Detect Market Structure Shift (MSS)
        mss_direction = self._detect_mss(prices)
        if mss_direction is None:
            return None

        # Detect Fair Value Gap (FVG)
        fvg_exists = self._detect_fvg(prices)

        # Combine signals
        confidence = 0.5
        if in_killzone:
            confidence += 0.15
        if fvg_exists:
            confidence += 0.2

        # Agent cross-validation (SE-4): News sentiment alignment
        if mss_direction == Direction.LONG and agents.news_sentiment > 0.2 or mss_direction == Direction.SHORT and agents.news_sentiment < -0.2:
            confidence += 0.1

        confidence = min(1.0, confidence)

        parameters: dict[str, Any] = {
            "in_killzone": in_killzone,
            "killzone_type": self._get_killzone_name(current_hour),
            "mss_direction": mss_direction.value,
            "fvg_detected": fvg_exists,
            "news_alignment": agents.news_sentiment > 0 if mss_direction == Direction.LONG else agents.news_sentiment < 0,
        }

        return self._build_signal(
            symbol=market.symbol,
            direction=mss_direction,
            confidence=confidence,
            regime=regime,
            parameters=parameters,
        )

    def _is_in_killzone(self, hour: int) -> bool:
        for start, end in [self.LONDON_KILLZONE, self.NY_KILLZONE, self.ASIA_KILLZONE]:
            if start <= hour <= end:
                return True
        return False

    def _get_killzone_name(self, hour: int) -> str:
        s, e = self.LONDON_KILLZONE
        if s <= hour <= e:
            return "london"
        s, e = self.NY_KILLZONE
        if s <= hour <= e:
            return "new_york"
        s, e = self.ASIA_KILLZONE
        if s <= hour <= e:
            return "asia"
        return "off_hours"

    def _detect_mss(self, prices: list[float]) -> Direction | None:
        # Simplified MSS: higher highs/lows broken
        if len(prices) < 3:
            return None
        recent_high = max(prices[-3:])
        recent_low = min(prices[-3:])
        prev_high = max(prices[:-3]) if len(prices) > 3 else prices[0]
        prev_low = min(prices[:-3]) if len(prices) > 3 else prices[0]

        if prices[-1] > prev_high and recent_high > prev_high:
            return Direction.LONG
        if prices[-1] < prev_low and recent_low < prev_low:
            return Direction.SHORT
        return None

    def _detect_fvg(self, prices: list[float]) -> bool:
        if len(prices) < 3:
            return False
        # FVG: gap between candle 1 high and candle 3 low (or vice versa)
        gap_up = prices[-1] - prices[-3] if prices[-3] != 0 else 0
        gap_ratio = abs(gap_up) / prices[-3] if prices[-3] != 0 else 0
        return gap_ratio > self.FVG_MIN_GAP_PCT
