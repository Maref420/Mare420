"""
Social Media Agent — Sensory agent for social sentiment and hype detection.

Processes social media events (Twitter/X, Reddit, Telegram) into
standardized AgentSignal outputs for strategy evaluators.

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


class SocialAgentProcessor:
    """
    Processes raw social media events into standardized signals.
    Pure processing unit — no I/O dependencies per TC-1.
    """

    HYPE_INDICATORS = frozenset({
        "moon", "rocket", "lambo", "100x", "gem", "pump",
        "going parabolic", "to the moon", "ape in",
    })
    FEAR_INDICATORS = frozenset({
        "rug pull", "scam", "dead", "dump", "panic", "sell everything",
        "capitulation", "going to zero", "rekt",
    })

    @classmethod
    def process_event(
        cls, raw_event: dict[str, Any], symbol: str
    ) -> AgentSignal | None:
        """
        Process a raw social media event into an AgentSignal.

        Args:
            raw_event: Dictionary containing social data.
            symbol: Trading symbol this social activity relates to.

        Returns:
            AgentSignal if processable, None if insufficient data.
        """
        text = raw_event.get("text", raw_event.get("content", ""))
        source_id = raw_event.get("post_id", raw_event.get("id", "unknown"))
        engagement = raw_event.get("engagement", {})

        if not text:
            return None

        text_lower = text.lower()
        score = cls._calculate_social_score(text_lower, engagement)
        sentiment = cls._score_to_sentiment(score)
        confidence = cls._calculate_social_confidence(engagement, text)

        signal = AgentSignal(
            agent_type=AgentType.SOCIAL,
            timestamp_utc=datetime.now(UTC),
            symbol=symbol,
            sentiment=sentiment,
            score=round(score, 4),
            confidence=round(confidence, 4),
            source_id=str(source_id),
            metadata={
                "platform": raw_event.get("platform", "unknown"),
                "hype_detected": any(kw in text_lower for kw in cls.HYPE_INDICATORS),
                "fear_detected": any(kw in text_lower for kw in cls.FEAR_INDICATORS),
            },
        )

        logger.info(
            "SOCIAL_SIGNAL_PRODUCED",
            extra={
                "symbol": symbol,
                "sentiment": sentiment.value,
                "score": round(score, 4),
            },
        )

        return signal

    @classmethod
    def _calculate_social_score(
        cls, text: str, engagement: dict[str, Any]
    ) -> float:
        """
        Calculate social sentiment score combining text analysis
        with engagement metrics.
        """
        hype_count = sum(1 for kw in cls.HYPE_INDICATORS if kw in text)
        fear_count = sum(1 for kw in cls.FEAR_INDICATORS if kw in text)
        total_keywords = hype_count + fear_count

        text_score: float = 0.0
        if total_keywords > 0:
            text_score = float(hype_count - fear_count) / float(total_keywords)

        # Extract engagement values with explicit type casting
        raw_likes = engagement.get("likes", 0)
        raw_shares = engagement.get("retweets", engagement.get("shares", 0))
        likes: float = float(raw_likes) if raw_likes is not None else 0.0
        shares: float = float(raw_shares) if raw_shares is not None else 0.0

        engagement_factor: float = min(1.0, (likes + shares * 2.0) / 1000.0)

        # Combine: text sentiment weighted by engagement
        combined: float = text_score * (0.5 + 0.5 * engagement_factor)
        result: float = max(-1.0, min(1.0, combined))
        return result

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
    def _calculate_social_confidence(
        cls, engagement: dict[str, Any], text: str
    ) -> float:
        """Higher engagement and longer text = higher confidence."""
        base = 0.2
        likes = engagement.get("likes", 0)
        if likes > 100:
            base += 0.2
        elif likes > 10:
            base += 0.1

        if len(text) > 50:
            base += 0.2
        if any(kw in text for kw in cls.HYPE_INDICATORS | cls.FEAR_INDICATORS):
            base += 0.2

        return min(1.0, base)


def merge_social_signals_into_context(
    signals: list[AgentSignal],
) -> float:
    """Aggregate multiple social signals into single hype index [0.0, 1.0]."""
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

    # Normalize from [-1, 1] to [0, 1] for hype index
    raw = weighted_sum / total_weight
    return max(0.0, min(1.0, (raw + 1.0) / 2.0))
