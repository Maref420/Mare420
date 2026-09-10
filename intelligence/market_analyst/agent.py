# MODULE: atlas-market-analyst
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: Analyzes combined microstructure + arbitrage signals.
# WARNING: No bare except. All exceptions handled explicitly.
# POLICY: Analysis only. No execution logic. Per CONSTITUTION.md v1.2.
from __future__ import annotations

import time

from intelligence.research_agent.arb_models import ArbitragePath
from intelligence.research_agent.models import ForensicsSignal

from .models import AnalystDecision, MarketAnalysis


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


class MarketAnalystAgent:
    """Analyzes combined microstructure and arbitrage signals."""

    def __init__(self) -> None:
        self._analyses_count: int = 0

    def analyze(
        self,
        forensics: ForensicsSignal,
        arb_paths: list[ArbitragePath] | None = None,
        trace_id: str = "",
    ) -> MarketAnalysis:
        """Produce unified MarketAnalysis from forensics and optional arb paths."""
        self._analyses_count += 1

        effective_trace = trace_id if trace_id else forensics.trace_id

        arb_paths is not None and len(arb_paths) > 0
        profitable_arbs = [p for p in (arb_paths or []) if p.profitable]
        arb_profitable = len(profitable_arbs) > 0
        best_weight = min((p.net_weight for p in profitable_arbs), default=0.0)
        exchange_count = max(
            (len(p.exchanges) for p in (arb_paths or [])),
            default=1,
        )

        base_confidence = forensics.confidence
        if arb_profitable:
            base_confidence += 0.1
        if forensics.spoofing_detected:
            base_confidence -= 0.3
        confidence = _clamp(base_confidence, 0.0, 1.0)

        if forensics.spoofing_detected:
            decision = AnalystDecision.INVESTIGATE
            reasoning = (
                f"Spoofing detected on {forensics.symbol}. "
                f"AQS={forensics.aqs_score}, confidence reduced."
            )
        elif arb_profitable and forensics.aqs_score >= 70:
            decision = AnalystDecision.STRONG_BUY_SIGNAL
            reasoning = (
                f"Strong signal: AQS={forensics.aqs_score}, "
                f"profitable arb paths={len(profitable_arbs)}, "
                f"best weight={best_weight:.4f}."
            )
        elif arb_profitable and forensics.aqs_score >= 50:
            decision = AnalystDecision.BUY_SIGNAL
            reasoning = (
                f"Buy signal with arb: AQS={forensics.aqs_score}, "
                f"profitable arb paths={len(profitable_arbs)}."
            )
        elif forensics.aqs_score >= 70:
            decision = AnalystDecision.BUY_SIGNAL
            reasoning = f"High AQS={forensics.aqs_score}, no spoofing."
        elif forensics.aqs_score >= 40:
            decision = AnalystDecision.HOLD
            reasoning = f"Moderate AQS={forensics.aqs_score}, holding position."
        else:
            decision = AnalystDecision.SELL_SIGNAL
            reasoning = f"Low AQS={forensics.aqs_score}, sell recommended."

        ts = forensics.timestamp_ns if forensics.timestamp_ns > 0 else int(time.time() * 1e9)

        return MarketAnalysis(
            symbol=forensics.symbol,
            decision=decision,
            confidence=confidence,
            aqs_score=forensics.aqs_score,
            spoofing_detected=forensics.spoofing_detected,
            arbitrage_profitable=arb_profitable,
            net_arb_weight=best_weight,
            exchange_count=exchange_count,
            reasoning=reasoning,
            trace_id=effective_trace,
            timestamp_ns=ts,
            source_uri="python-market-analyst://v1",
        )

    @property
    def analyses_count(self) -> int:
        return self._analyses_count
