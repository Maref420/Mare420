"""
Wallet Tracker Agent — Sensory agent for whale movement detection.

Processes on-chain wallet events (exchange inflows/outflows, large transfers)
into standardized AgentSignal outputs for strategy evaluators.

Governed by:
- SE-4: Agent Cross-Validation (critical for SMC and Iceberg strategies)
- Rule 12: Minimal Blast Radius
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from intelligence.sensory_agents.models import (
    AgentSignal,
    AgentType,
    SentimentLevel,
)

logger = logging.getLogger(__name__)


# Minimum USD value to classify as whale movement
WHALE_THRESHOLD_USD = 100_000.0


class WalletAgentProcessor:
    """
    Processes raw wallet/on-chain events into standardized signals.
    Pure processing unit — no I/O dependencies per TC-1.
    """

    @classmethod
    def process_event(
        cls, raw_event: dict[str, Any], symbol: str
    ) -> AgentSignal | None:
        """
        Process a raw wallet event into an AgentSignal.

        Args:
            raw_event: Dictionary containing on-chain data.
                Expected keys: type (inflow/outflow/transfer),
                amount_usd, from_address, to_address, tx_hash
            symbol: Trading symbol this wallet activity relates to.

        Returns:
            AgentSignal if processable, None if below whale threshold.
        """
        event_type = raw_event.get("type", "unknown")
        amount_usd = raw_event.get("amount_usd", 0.0)
        tx_hash = raw_event.get("tx_hash", raw_event.get("id", "unknown"))

        if not isinstance(amount_usd, (int, float)):
            return None

        # Filter: Only process whale-level movements
        if amount_usd < WHALE_THRESHOLD_USD:
            return None

        score = cls._calculate_wallet_score(event_type, amount_usd)
        sentiment = cls._score_to_sentiment(score)
        confidence = cls._calculate_wallet_confidence(amount_usd, event_type)

        signal = AgentSignal(
            agent_type=AgentType.WALLET,
            timestamp_utc=datetime.now(UTC),
            symbol=symbol,
            sentiment=sentiment,
            score=round(score, 4),
            confidence=round(confidence, 4),
            source_id=str(tx_hash),
            metadata={
                "event_type": event_type,
                "amount_usd": round(amount_usd, 2),
                "from_address": raw_event.get("from_address", ""),
                "to_address": raw_event.get("to_address", ""),
                "is_exchange_inflow": event_type == "exchange_inflow",
                "is_exchange_outflow": event_type == "exchange_outflow",
            },
        )

        logger.info(
            "WALLET_SIGNAL_PRODUCED",
            extra={
                "symbol": symbol,
                "event_type": event_type,
                "amount_usd": round(amount_usd, 2),
                "score": round(score, 4),
            },
        )

        return signal

    @classmethod
    def _calculate_wallet_score(cls, event_type: str, amount_usd: float) -> float:
        """
        Calculate wallet flow score.

        Exchange inflow (whales sending to exchange) = bearish (potential sell)
        Exchange outflow (whales withdrawing) = bullish (accumulation)
        """
        magnitude = min(1.0, amount_usd / 1_000_000.0)  # Normalize at $1M

        if event_type == "exchange_inflow":
            return -magnitude  # Bearish
        if event_type == "exchange_outflow":
            return magnitude   # Bullish
        if event_type == "whale_transfer":
            return 0.0         # Neutral — internal transfer
        return 0.0

    @classmethod
    def _score_to_sentiment(cls, score: float) -> SentimentLevel:
        if score >= 0.6:
            return SentimentLevel.VERY_BULLISH
        if score >= 0.2:
            return SentimentLevel.BULLISH
        if score <= -0.6:
            return SentimentLevel.VERY_BEARISH
        if score <= -0.2:
            return SentimentLevel.BEARISH
        return SentimentLevel.NEUTRAL

    @classmethod
    def _calculate_wallet_confidence(
        cls, amount_usd: float, event_type: str
    ) -> float:
        """Larger amounts and clear exchange flows = higher confidence."""
        base = 0.4
        if amount_usd > 500_000:
            base += 0.3
        elif amount_usd > 200_000:
            base += 0.15

        if event_type in ("exchange_inflow", "exchange_outflow"):
            base += 0.2

        return min(1.0, base)


def compute_wallet_context(
    signals: list[AgentSignal],
) -> tuple[float, float]:
    """
    Aggregate wallet signals into two context values.

    Returns:
        Tuple of (whale_flow, exchange_inflow) both in [-1.0, 1.0].
        whale_flow: positive = accumulation, negative = distribution
        exchange_inflow: positive = coins flowing TO exchanges (bearish)
    """
    if not signals:
        return 0.0, 0.0

    total_weight = 0.0
    flow_sum = 0.0
    inflow_sum = 0.0

    for sig in signals:
        weight = sig.confidence
        flow_sum += sig.score * weight
        total_weight += weight

        meta = sig.metadata or {}
        if meta.get("is_exchange_inflow"):
            inflow_sum += weight
        elif meta.get("is_exchange_outflow"):
            inflow_sum -= weight

    if total_weight == 0.0:
        return 0.0, 0.0

    whale_flow = max(-1.0, min(1.0, flow_sum / total_weight))
    exchange_inflow = max(-1.0, min(1.0, inflow_sum / total_weight))

    return whale_flow, exchange_inflow
