"""
Strategy 4: Volume Strategy Evaluator.
Analyzes volume-price divergence and climax detection.

Logic: When price moves up but volume decreases = bearish divergence.
When price moves down but volume decreases = bullish divergence.
Volume climax (extreme spike) often marks reversal points.

Governed by: SE-2, SE-3
"""
from __future__ import annotations

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


class VolumeEvaluator(BaseStrategyEvaluator):
    """Evaluates volume-price relationships for trade signals."""

    CLIMAX_MULTIPLIER = 3.0
    DIVERGENCE_THRESHOLD = 0.001

    @property
    def strategy_name(self) -> str:
        return "volume_evaluator_v1"

    def evaluate(
        self,
        market: MarketSnapshot,
        agents: AgentContext,
        regime: Regime,
    ) -> StrategySignalEventV1 | None:
        trades = market.trades
        if len(trades) < 5:
            return None

        # Extract volumes and prices
        volumes: list[float] = []
        prices: list[float] = []
        for trade in trades:
            vol = trade.get("quantity") or trade.get("q") or trade.get("size", 0.0)
            price = trade.get("price") or trade.get("p", 0.0)
            if isinstance(vol, (int, float)) and isinstance(price, (int, float)):
                volumes.append(float(vol))
                prices.append(float(price))

        if len(volumes) < 5 or len(prices) < 5:
            return None

        # Calculate recent vs earlier volume
        half = len(volumes) // 2
        early_vol = sum(volumes[:half]) / max(half, 1)
        recent_vol = sum(volumes[half:]) / max(len(volumes) - half, 1)

        # Price movement
        price_change = (prices[-1] - prices[0]) / prices[0] if prices[0] != 0 else 0.0
        vol_change = (recent_vol - early_vol) / early_vol if early_vol != 0 else 0.0

        # Detect volume climax
        is_climax = recent_vol > early_vol * self.CLIMAX_MULTIPLIER if early_vol > 0 else False

        # Divergence detection
        direction: Direction | None = None
        confidence = 0.0

        if is_climax:
            # Volume climax often precedes reversal
            if price_change > self.DIVERGENCE_THRESHOLD:
                direction = Direction.SHORT  # Price up + climax = reversal down
                confidence = 0.75
            elif price_change < -self.DIVERGENCE_THRESHOLD:
                direction = Direction.LONG   # Price down + climax = reversal up
                confidence = 0.75
        elif price_change > self.DIVERGENCE_THRESHOLD and vol_change < -0.2:
            # Price rising but volume declining = bearish divergence
            direction = Direction.SHORT
            confidence = 0.6
        elif price_change < -self.DIVERGENCE_THRESHOLD and vol_change < -0.2:
            # Price falling but volume declining = bullish divergence
            direction = Direction.LONG
            confidence = 0.6
        elif price_change > self.DIVERGENCE_THRESHOLD and vol_change > 0.3:
            # Price rising with increasing volume = genuine trend
            direction = Direction.LONG
            confidence = 0.7
        elif price_change < -self.DIVERGENCE_THRESHOLD and vol_change > 0.3:
            # Price falling with increasing volume = genuine downtrend
            direction = Direction.SHORT
            confidence = 0.7

        if direction is None:
            return None

        parameters: dict[str, Any] = {
            "price_change_pct": round(price_change, 6),
            "volume_change_pct": round(vol_change, 4),
            "is_climax": is_climax,
            "early_avg_volume": round(early_vol, 4),
            "recent_avg_volume": round(recent_vol, 4),
        }

        return self._build_signal(
            symbol=market.symbol,
            direction=direction,
            confidence=confidence,
            regime=regime,
            parameters=parameters,
        )
