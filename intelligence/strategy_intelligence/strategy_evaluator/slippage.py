"""
Strategy 1: Price Slippage Evaluator.
Detects expected slippage based on order book depth vs trade size.

Logic: Compares spread and cumulative liquidity at top-of-book
against historical average to identify abnormal slippage conditions.
When slippage is abnormally high, signals FLAT (avoid entry).
When slippage is low (deep liquidity), confirms directional signal.

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


class SlippageEvaluator(BaseStrategyEvaluator):
    """Evaluates price slippage risk from order book depth."""

    # Thresholds for slippage assessment
    SPREAD_TIGHT_THRESHOLD = 0.0005   # 0.05% spread = tight
    SPREAD_WIDE_THRESHOLD = 0.003     # 0.3% spread = wide
    MIN_LIQUIDITY_LEVELS = 5          # Minimum orderbook levels needed

    @property
    def strategy_name(self) -> str:
        return "slippage_evaluator_v1"

    def evaluate(
        self,
        market: MarketSnapshot,
        agents: AgentContext,
        regime: Regime,
    ) -> StrategySignalEventV1 | None:
        if not market.orderbook_bids or not market.orderbook_asks:
            return None

        spread = self._calculate_spread(market)
        bid_depth = self._calculate_depth(market.orderbook_bids)
        ask_depth = self._calculate_depth(market.orderbook_asks)
        imbalance = self._calculate_imbalance(bid_depth, ask_depth)

        # Determine direction based on orderbook imbalance
        if spread > self.SPREAD_WIDE_THRESHOLD:
            # Wide spread = high slippage risk, avoid trading
            direction = Direction.FLAT
            confidence = 0.8
        elif imbalance > 0.15:
            # More bid liquidity = bullish pressure
            direction = Direction.LONG
            confidence = min(0.9, abs(imbalance))
        elif imbalance < -0.15:
            # More ask liquidity = bearish pressure
            direction = Direction.SHORT
            confidence = min(0.9, abs(imbalance))
        else:
            return None  # No clear signal

        parameters: dict[str, Any] = {
            "spread": round(spread, 6),
            "bid_depth": round(bid_depth, 2),
            "ask_depth": round(ask_depth, 2),
            "imbalance": round(imbalance, 4),
        }

        return self._build_signal(
            symbol=market.symbol,
            direction=direction,
            confidence=confidence,
            regime=regime,
            parameters=parameters,
        )

    def _calculate_spread(self, market: MarketSnapshot) -> float:
        best_bid = market.orderbook_bids[0][0] if market.orderbook_bids else 0.0
        best_ask = market.orderbook_asks[0][0] if market.orderbook_asks else 0.0
        if best_bid == 0.0:
            return 1.0
        return (best_ask - best_bid) / best_bid

    def _calculate_depth(self, levels: list[tuple[float, float]]) -> float:
        # Sum quantity of top N levels
        depth_levels = levels[:self.MIN_LIQUIDITY_LEVELS]
        return sum(qty for _, qty in depth_levels)

    def _calculate_imbalance(self, bid_depth: float, ask_depth: float) -> float:
        total = bid_depth + ask_depth
        if total == 0.0:
            return 0.0
        return (bid_depth - ask_depth) / total
