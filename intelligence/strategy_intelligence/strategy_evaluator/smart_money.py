"""
Strategy 3: Smart Money Concepts (SMC) & Trap Evaluator.
Identifies liquidity sweeps, fake breakouts, and institutional traps.

Logic: Combines order book analysis with wallet tracker data to detect
when smart money is engineering false moves to trap retail traders.
A bull trap occurs when price breaks resistance with low volume while
whales distribute. A bear trap is the inverse.

Agent Cross-Validation (SE-4): Uses wallet_whale_flow to confirm
whether a breakout is genuine or a trap.

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


class SmartMoneyEvaluator(BaseStrategyEvaluator):
    """Detects SMC patterns: liquidity sweeps, order blocks, traps."""

    WHALE_DIVERGENCE_THRESHOLD = 0.3
    VOLUME_SPIKE_MULTIPLIER = 2.0

    @property
    def strategy_name(self) -> str:
        return "smart_money_evaluator_v1"

    def evaluate(
        self,
        market: MarketSnapshot,
        agents: AgentContext,
        regime: Regime,
    ) -> StrategySignalEventV1 | None:
        if not market.orderbook_bids or not market.orderbook_asks:
            return None

        # Detect liquidity sweep (large cluster of stops above/below)
        sweep_type = self._detect_liquidity_sweep(market)

        # Cross-validate with wallet data (SE-4)
        whale_flow = agents.wallet_whale_flow
        is_trap = False
        trap_type = "NONE"

        if sweep_type == "buy_side_sweep" and whale_flow < -self.WHALE_DIVERGENCE_THRESHOLD:
            # Price swept buy-side liquidity but whales are selling = BULL TRAP
            is_trap = True
            trap_type = "BULL_TRAP"
        elif sweep_type == "sell_side_sweep" and whale_flow > self.WHALE_DIVERGENCE_THRESHOLD:
            # Price swept sell-side liquidity but whales are buying = BEAR TRAP
            is_trap = True
            trap_type = "BEAR_TRAP"

        if not is_trap:
            # Check for genuine order block
            ob_direction = self._detect_order_block(market, whale_flow)
            if ob_direction is None:
                return None
            direction = ob_direction
            confidence = 0.6 + min(0.3, abs(whale_flow) * 0.3)
        else:
            # Trade AGAINST the trap
            direction = Direction.SHORT if trap_type == "BULL_TRAP" else Direction.LONG
            confidence = 0.7 + min(0.25, abs(whale_flow) * 0.2)

        parameters: dict[str, Any] = {
            "trap_detected": is_trap,
            "trap_type": trap_type,
            "sweep_type": sweep_type or "none",
            "whale_flow": round(whale_flow, 4),
        }

        return self._build_signal(
            symbol=market.symbol,
            direction=direction,
            confidence=confidence,
            regime=regime,
            parameters=parameters,
        )

    def _detect_liquidity_sweep(self, market: MarketSnapshot) -> str | None:
        # Simplified: check if large liquidity clusters exist far from mid price
        if not market.orderbook_bids or not market.orderbook_asks:
            return None

        mid_price = (market.bid + market.ask) / 2.0 if market.bid and market.ask else market.last_price
        if mid_price == 0.0:
            return None

        # Check for large ask walls (buy-side liquidity)
        max_ask_qty = max((qty for _, qty in market.orderbook_asks[:10]), default=0.0)
        avg_ask_qty = sum(qty for _, qty in market.orderbook_asks[:10]) / min(10, len(market.orderbook_asks)) if market.orderbook_asks else 0.0

        # Check for large bid walls (sell-side liquidity)
        max_bid_qty = max((qty for _, qty in market.orderbook_bids[:10]), default=0.0)
        avg_bid_qty = sum(qty for _, qty in market.orderbook_bids[:10]) / min(10, len(market.orderbook_bids)) if market.orderbook_bids else 0.0

        if avg_ask_qty > 0 and max_bid_qty > avg_bid_qty * self.VOLUME_SPIKE_MULTIPLIER:
            return "sell_side_sweep"
        if avg_bid_qty > 0 and max_ask_qty > avg_ask_qty * self.VOLUME_SPIKE_MULTIPLIER:
            return "buy_side_sweep"
        return None

    def _detect_order_block(
        self, market: MarketSnapshot, whale_flow: float
    ) -> Direction | None:
        # Order block: accumulation zone where smart money placed orders
        if whale_flow > self.WHALE_DIVERGENCE_THRESHOLD:
            return Direction.LONG
        if whale_flow < -self.WHALE_DIVERGENCE_THRESHOLD:
            return Direction.SHORT
        return None
