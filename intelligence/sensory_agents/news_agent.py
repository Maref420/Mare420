"""
News Agent — Sensory agent for news sentiment analysis.

Subscribes to atlas.news.raw.v1 NATS topic, processes raw news events,
and produces standardized AgentSignal outputs for strategy evaluators.

Governed by:
- SE-4: Agent Cross-Validation
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


class NewsAgentProcessor:
    """
    Processes raw news events into standardized signals.

    This is NOT a NATS subscriber itself — it is a pure processing unit
    that can be called by any transport layer (NATS, HTTP, direct).
    Governed by TC-1: Strict Hemispheric Isolation.
    """

    # Keyword-based sentiment scoring (baseline until ML model trained)
    BULLISH_KEYWORDS = frozenset({
        "approval", "launch", "partnership", "adoption", "surge",
        "breakout", "upgrade", "bullish", "institutional", "inflow",
        "etf approved", "accumulation", "buyback",
    })
    BEARISH_KEYWORDS = frozenset({
        "hack", "exploit", "ban", "lawsuit", "sec", "crash",
        "dump", "bearish", "outflow", "liquidation", "fraud",
        "investigation", "fine", "penalty", "delay",
    })

    @classmethod
    def process_event(
        cls, raw_event: dict[str, Any], symbol: str
    ) -> AgentSignal | None:
        """
        Process a raw news event into an AgentSignal.

        Args:
            raw_event: Dictionary containing news data from ingestion.
            symbol: Trading symbol this news relates to.

        Returns:
            AgentSignal if processable, None if insufficient data.
        """
        headline = raw_event.get("headline", "")
        body = raw_event.get("body", "")
        source_id = raw_event.get("url", raw_event.get("id", "unknown"))

        if not headline and not body:
            logger.warning("NEWS_EVENT_EMPTY", extra={"source_id": source_id})
            return None

        text = f"{headline} {body}".lower()
        score = cls._calculate_sentiment(text)
        sentiment = cls._score_to_sentiment(score)
        confidence = cls._calculate_confidence(text, headline)

        signal = AgentSignal(
            agent_type=AgentType.NEWS,
            timestamp_utc=datetime.now(UTC),
            symbol=symbol,
            sentiment=sentiment,
            score=round(score, 4),
            confidence=round(confidence, 4),
            source_id=str(source_id),
            metadata={"headline_length": len(headline)},
        )

        logger.info(
            "NEWS_SIGNAL_PRODUCED",
            extra={
                "symbol": symbol,
                "sentiment": sentiment.value,
                "score": round(score, 4),
                "confidence": round(confidence, 4),
            },
        )

        return signal

    @classmethod
    def _calculate_sentiment(cls, text: str) -> float:
        """
        Calculate sentiment score from text using keyword matching.
        Returns float in [-1.0, 1.0].
        """
        bull_count = sum(1 for kw in cls.BULLISH_KEYWORDS if kw in text)
        bear_count = sum(1 for kw in cls.BEARISH_KEYWORDS if kw in text)
        total = bull_count + bear_count

        if total == 0:
            return 0.0

        return (bull_count - bear_count) / total

    @classmethod
    def _score_to_sentiment(cls, score: float) -> SentimentLevel:
        """Map numeric score to categorical sentiment level."""
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
    def _calculate_confidence(cls, text: str, headline: str) -> float:
        """
        Calculate confidence based on text quality indicators.
        Longer headlines and more keyword matches = higher confidence.
        """
        base_confidence = 0.3
        if len(headline) > 20:
            base_confidence += 0.2
        if len(text) > 100:
            base_confidence += 0.2

        keyword_hits = sum(
            1 for kw in cls.BULLISH_KEYWORDS | cls.BEARISH_KEYWORDS
            if kw in text
        )
        base_confidence += min(0.3, keyword_hits * 0.05)

        return min(1.0, base_confidence)


def merge_news_signals_into_context(
    signals: list[AgentSignal],
) -> float:
    """
    Aggregate multiple news signals into single context value.
    Uses confidence-weighted average of scores.
    """
    if not signals:
        return 0.0

    total_weight = 0.0
    weighted_sum = 0.0

    for sig in signals:
        weight = sig.confidence
        weighted_sum += sig.score * weight
        total_weight += weight

    if total_weight == 0.0:
        return 0.0

    return max(-1.0, min(1.0, weighted_sum / total_weight))
