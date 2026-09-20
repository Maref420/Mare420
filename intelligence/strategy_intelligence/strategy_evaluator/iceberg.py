"""
Strategy 6: Iceberg Order Evaluator.
Detects hidden institutional orders through repeated fills at same level.

Logic: Iceberg orders are large institutional orders split into small
visible chunks. Detection relies on identifying repeated trades at
identical price levels with unusual frequency, correlated with
wallet tracker exchange inflow/outflow data.

Agent Cross-Validation (SE-4): wallet_exchange_inflow confirms
institutional activity at detected price level.

Governed by: SE-2, SE-3, SE-4
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


class IcebergEvaluator(BaseStrategyEvaluator):
    """Detects iceberg (hidden institutional) orders."""

    MIN_REPEAT_FILLS = 5
    PRICE_CLUSTER_TOLERANCE = 0.0001  # 0.01% tolerance for same-level grouping
    EXCHANGE_FLOW_THRESHOLD = 0.2

    @property
    def strategy_name(self) -> str:
        return "iceberg_evaluator_v1"

    def evaluate(
        self,
        market: MarketSnapshot,
        agents: AgentContext,
        regime: Regime,
    ) -> StrategySignalEventV1 | None:
        trades = market.trades
        if len(trades) < self.MIN_REPEAT_FILLS:
            return None

        # Group trades by price clusters
        price_levels = self._cluster_prices(trades)
        if not price_levels:
            return None

        # Find iceberg candidates (levels with unusually many fills)
        iceberg_level = None
        iceberg_count = 0
        iceberg_side = "unknown"

        for level_price, level_trades in price_levels.items():
            if len(level_trades) >= self.MIN_REPEAT_FILLS and len(level_trades) > iceberg_count:
                iceberg_count = len(level_trades)
                iceberg_level = level_price
                iceberg_side = self._determine_side(level_trades, market.last_price)

        if iceberg_level is None:
            return None

        # Cross-validate with wallet data (SE-4)
        exchange_inflow = agents.wallet_exchange_inflow
        whale_flow = agents.wallet_whale_flow

        # Determine direction based on iceberg side + wallet confirmation
        if iceberg_side == "buy" and exchange_inflow > self.EXCHANGE_FLOW_THRESHOLD:
            # Large buys at same level + coins flowing to exchange = distribution
            direction = Direction.SHORT
            confidence = 0.65
        elif iceberg_side == "sell" and exchange_inflow < -self.EXCHANGE_FLOW_THRESHOLD:
            # Large sells at same level + coins leaving exchange = accumulation
            direction = Direction.LONG
            confidence = 0.65
        elif iceberg_side == "buy" and whale_flow > self.EXCHANGE_FLOW_THRESHOLD:
            direction = Direction.LONG
            confidence = 0.7
        elif iceberg_side == "sell" and whale_flow < -self.EXCHANGE_FLOW_THRESHOLD:
            direction = Direction.SHORT
            confidence = 0.7
        else:
            # Detected iceberg but no wallet confirmation
            direction = Direction.FLAT
            confidence = 0.4

        # Estimate iceberg size
        total_volume = sum(
            float(t.get("quantity", t.get("q", t.get("size", 0))))
            for t in trades
            if isinstance(t.get("quantity", t.get("q", t.get("size", 0))), (int, float))
        )

        parameters: dict[str, Any] = {
            "iceberg_detected": True,
            "iceberg_price": iceberg_level,
            "fill_count": iceberg_count,
            "iceberg_side": iceberg_side,
            "estimated_volume": round(total_volume, 4),
            "exchange_inflow": round(exchange_inflow, 4),
            "whale_flow": round(whale_flow, 4),
        }

        return self._build_signal(
            symbol=market.symbol,
            direction=direction,
            confidence=confidence,
            regime=regime,
            parameters=parameters,
        )

    def _cluster_prices(self, trades: list[dict[str, Any]]) -> dict[float, list[dict[str, Any]]]:
        clusters: dict[float, list[dict[str, Any]]] = {}
        for trade in trades:
            price = trade.get("price") or trade.get("p", 0.0)
            if not isinstance(price, (int, float)) or price == 0:
                continue
            price_f = float(price)

            # Find existing cluster within tolerance
            matched = False
            for cluster_price in clusters:
                if abs(price_f - cluster_price) / cluster_price <= self.PRICE_CLUSTER_TOLERANCE:
                    clusters[cluster_price].append(trade)
                    matched = True
                    break
            if not matched:
                clusters[price_f] = [trade]
        return clusters

    def _determine_side(self, level_trades: list[dict[str, Any]], last_price: float) -> str:
        if not level_trades or last_price == 0:
            return "unknown"
        avg_price = sum(
            float(t.get("price", t.get("p", last_price)))
            for t in level_trades
            if isinstance(t.get("price", t.get("p", last_price)), (int, float))
        ) / len(level_trades)

        if avg_price >= last_price:
            return "sell"  # Selling at/above market
        return "buy"  # Buying at/below market
