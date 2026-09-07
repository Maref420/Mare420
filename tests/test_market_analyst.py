# MODULE: atlas-tests
# GOVERNANCE: Test suite for MarketAnalystAgent.
from __future__ import annotations

import json

import pytest

from intelligence.market_analyst.models import AnalystDecision, MarketAnalysis
from intelligence.market_analyst.agent import MarketAnalystAgent
from intelligence.research_agent.models import ForensicsSignal
from intelligence.research_agent.arb_models import ArbitragePath


def _make_forensics(
    symbol: str = "BTCUSDT",
    aqs: int = 70,
    confidence: float = 0.8,
    spoofing: bool = False,
) -> ForensicsSignal:
    return ForensicsSignal(
        symbol=symbol,
        raw_spread_bps=10,
        aqs_score=aqs,
        confidence=confidence,
        orderbook_imbalance=0.5,
        vpin_toxicity=0.2,
        spoofing_detected=spoofing,
        trace_id="test-trace-1",
        timestamp_ns=1_725_148_800_000_000_000,
        source_uri="rust-feature-engine://v1",
    )


def _make_arb(profitable: bool = True) -> ArbitragePath:
    return ArbitragePath(
        exchanges=["binance", "okx", "bybit"],
        symbol="BTCUSDT",
        net_weight=-0.003 if profitable else 0.05,
        hop_count=3,
        profitable=profitable,
        timestamp_ns=1_725_148_800_000_000_000,
        source_uri="rust-arb-graph://v1",
    )


class TestMarketAnalystAgent:
    def setup_method(self) -> None:
        self.agent = MarketAnalystAgent()

    def test_strong_buy_signal_with_arb(self) -> None:
        f = _make_forensics(aqs=85)
        result = self.agent.analyze(f, [_make_arb(True)])
        assert result.decision == AnalystDecision.STRONG_BUY_SIGNAL
        assert result.arbitrage_profitable is True

    def test_buy_signal_no_arb(self) -> None:
        f = _make_forensics(aqs=75)
        result = self.agent.analyze(f)
        assert result.decision == AnalystDecision.BUY_SIGNAL

    def test_hold_low_aqs(self) -> None:
        f = _make_forensics(aqs=50)
        result = self.agent.analyze(f)
        assert result.decision == AnalystDecision.HOLD

    def test_sell_signal_very_low(self) -> None:
        f = _make_forensics(aqs=20)
        result = self.agent.analyze(f)
        assert result.decision == AnalystDecision.SELL_SIGNAL

    def test_investigate_on_spoofing(self) -> None:
        f = _make_forensics(aqs=90, spoofing=True)
        result = self.agent.analyze(f)
        assert result.decision == AnalystDecision.INVESTIGATE
        assert result.spoofing_detected is True

    def test_confidence_clamped_high(self) -> None:
        f = _make_forensics(confidence=0.95)
        result = self.agent.analyze(f, [_make_arb(True)])
        assert result.confidence <= 1.0

    def test_confidence_clamped_low(self) -> None:
        f = _make_forensics(confidence=0.1, spoofing=True)
        result = self.agent.analyze(f)
        assert result.confidence >= 0.0

    def test_none_arb_paths_handled(self) -> None:
        f = _make_forensics()
        result = self.agent.analyze(f, None)
        assert result.arbitrage_profitable is False

    def test_empty_arb_paths_handled(self) -> None:
        f = _make_forensics()
        result = self.agent.analyze(f, [])
        assert result.arbitrage_profitable is False

    def test_source_uri_set(self) -> None:
        f = _make_forensics()
        result = self.agent.analyze(f)
        assert result.source_uri == "python-market-analyst://v1"

    def test_trace_id_propagated(self) -> None:
        f = _make_forensics()
        result = self.agent.analyze(f, trace_id="custom-trace")
        assert result.trace_id == "custom-trace"

    def test_trace_id_fallback_to_forensics(self) -> None:
        f = _make_forensics()
        result = self.agent.analyze(f)
        assert result.trace_id == "test-trace-1"

    def test_serialization_roundtrip(self) -> None:
        f = _make_forensics()
        result = self.agent.analyze(f)
        data = result.model_dump_json()
        parsed = MarketAnalysis.model_validate_json(data)
        assert parsed.symbol == result.symbol
        assert parsed.decision == result.decision

    def test_frozen_model(self) -> None:
        f = _make_forensics()
        result = self.agent.analyze(f)
        with pytest.raises(Exception):
            result.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_analyses_count_increments(self) -> None:
        assert self.agent.analyses_count == 0
        f = _make_forensics()
        self.agent.analyze(f)
        assert self.agent.analyses_count == 1
        self.agent.analyze(f)
        assert self.agent.analyses_count == 2

    def test_reasoning_not_empty(self) -> None:
        f = _make_forensics()
        result = self.agent.analyze(f)
        assert len(result.reasoning) > 0

    def test_buy_signal_with_arb_moderate_aqs(self) -> None:
        f = _make_forensics(aqs=55)
        result = self.agent.analyze(f, [_make_arb(True)])
        assert result.decision == AnalystDecision.BUY_SIGNAL

    def test_exchange_count_from_arb(self) -> None:
        f = _make_forensics()
        result = self.agent.analyze(f, [_make_arb(True)])
        assert result.exchange_count == 3

    def test_exchange_count_default_no_arb(self) -> None:
        f = _make_forensics()
        result = self.agent.analyze(f)
        assert result.exchange_count == 1
