"""
Strategy 2: Price Slip Evaluator.
Detects sudden price displacement patterns indicating momentum acceleration.

Logic: Analyzes tick-by-tick trades for rapid sequential price movements
in one direction. A slip differs from slippage — it is the actual price
displacement caused by aggressive market orders consuming liquidity.

Governed by: SE-2 (Schema Compliance), SE-3 (No Single Execution)
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


class PriceSlipEvaluator(BaseStrategyEvaluator):
    """Detects sudden price displacement from aggressive order flow."""

    MIN_TRADES_FOR_SLIP = 10
    SLIP_THRESHOLD_PCT = 0.002  # 0.2% rapid move = slip detected

    @property
    def strategy_name(self) -> str:
        return "price_slip_evaluator_v1"

    def evaluate(
        self,
        market: MarketSnapshot,
        agents: AgentContext,
        regime: Regime,
    ) -> StrategySignalEventV1 | None:
        trades = market.trades
        if len(trades) < self.MIN_TRADES_FOR_SLIP:
            return None

        # Extract prices from recent trades
        prices: list[float] = []
        for trade in trades[-self.MIN_TRADES_FOR_SLIP:]:
            price = trade.get("price") or trade.get("p", 0.0)
            if isinstance(price, (int, float)) and price > 0:
                prices.append(float(price))

        if len(prices) < self.MIN_TRADES_FOR_SLIP:
            return None

        # Calculate displacement
        first_price = prices[0]
        last_price = prices[-1]
        if first_price == 0.0:
            return None

        displacement = (last_price - first_price) / first_price
        abs_displacement = abs(displacement)

        if abs_displacement < self.SLIP_THRESHOLD_PCT:
            return None  # No significant slip

        # Determine direction
        if displacement > 0:
            direction = Direction.LONG
        elif displacement < 0:
            direction = Direction.SHORT
        else:
            return None

        # Confidence scales with displacement magnitude
        confidence = min(1.0, abs_displacement / (self.SLIP_THRESHOLD_PCT * 3))

        # Count consecutive same-direction ticks
        consecutive = self._count_consecutive_direction(prices)

        parameters: dict[str, Any] = {
            "displacement_pct": round(displacement, 6),
            "consecutive_ticks": consecutive,
            "trade_count": len(prices),
        }

        return self._build_signal(
            symbol=market.symbol,
            direction=direction,
            confidence=confidence,
            regime=regime,
            parameters=parameters,
        )

    def _count_consecutive_direction(self, prices: list[float]) -> int:
        if len(prices) < 2:
            return 0
        direction = 1 if prices[-1] > prices[-2] else -1
        count = 0
        for i in range(len(prices) - 1, 0, -1):
            step = 1 if prices[i] > prices[i - 1] else (-1 if prices[i] < prices[i - 1] else 0)
            if step == direction:
                count += 1
            else:
                break
        return count
