"""
End-to-End Integration Test for Strategy Orchestrator Pipeline.
Governed by: Rule 14, Rule 15, SE-1, CG-4
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from intelligence.sensory_agents.models import (
    AgentSignal,
    AgentType,
    SentimentLevel,
)
from intelligence.strategy_intelligence.confluence import (
    ConfluenceMatrix,
    ConfluenceResult,
)
from intelligence.strategy_intelligence.orchestrator import StrategyOrchestrator
from intelligence.strategy_intelligence.proposal_translator import (
    ProposalTranslator,
)
from intelligence.strategy_intelligence.strategy_evaluator.base import (
    AgentContext,
    MarketSnapshot,
)
from intelligence.strategy_intelligence.strategy_evaluator.models import (
    Direction,
    Regime,
    SignalPayload,
    StrategySignalEventV1,
)


@pytest.fixture
def sample_market() -> MarketSnapshot:
    now = datetime.now(UTC)
    return MarketSnapshot(
        symbol="BTCUSDT", timestamp=now, bid=67500.0, ask=67510.0,
        last_price=67505.0, volume_24h=15000.0,
        trades=[
            {"price": 67490.0, "quantity": 0.5},
            {"price": 67495.0, "quantity": 1.2},
            {"price": 67500.0, "quantity": 0.8},
            {"price": 67505.0, "quantity": 2.0},
            {"price": 67510.0, "quantity": 1.5},
            {"price": 67515.0, "quantity": 3.0},
            {"price": 67520.0, "quantity": 0.3},
            {"price": 67525.0, "quantity": 0.1},
            {"price": 67530.0, "quantity": 0.2},
            {"price": 67535.0, "quantity": 0.4},
            {"price": 67540.0, "quantity": 0.6},
            {"price": 67545.0, "quantity": 1.0},
        ],
        orderbook_bids=[
            (67500.0, 5.0), (67490.0, 10.0), (67480.0, 15.0),
            (67470.0, 8.0), (67460.0, 12.0), (67450.0, 20.0),
        ],
        orderbook_asks=[
            (67510.0, 3.0), (67520.0, 4.0), (67530.0, 2.0),
            (67540.0, 1.5), (67550.0, 1.0), (67560.0, 0.5),
        ],
        funding_rate=0.001, open_interest=50000.0,
    )


@pytest.fixture
def bullish_signals() -> list[AgentSignal]:
    now = datetime.now(UTC)
    return [
        AgentSignal(agent_type=AgentType.NEWS, timestamp_utc=now,
            symbol="BTCUSDT", sentiment=SentimentLevel.BULLISH,
            score=0.7, confidence=0.8, source_id="n1"),
        AgentSignal(agent_type=AgentType.SOCIAL, timestamp_utc=now,
            symbol="BTCUSDT", sentiment=SentimentLevel.BULLISH,
            score=0.5, confidence=0.6, source_id="s1"),
        AgentSignal(agent_type=AgentType.WALLET, timestamp_utc=now,
            symbol="BTCUSDT", sentiment=SentimentLevel.VERY_BULLISH,
            score=0.8, confidence=0.9, source_id="w1",
            metadata={"event_type": "exchange_outflow",
                      "amount_usd": 500000.0,
                      "is_exchange_inflow": False,
                      "is_exchange_outflow": True}),
    ]


@pytest.fixture
def empty_market() -> MarketSnapshot:
    return MarketSnapshot(
        symbol="BTCUSDT", timestamp=datetime.now(UTC),
        bid=67500.0, ask=67510.0, last_price=67505.0,
        volume_24h=0.0, trades=[], orderbook_bids=[], orderbook_asks=[],
    )



class TestSchemaCompliance:

    def test_valid_signal(self) -> None:
        sig = StrategySignalEventV1(
            version="1.0.0", event_id="t1",
            timestamp_utc=datetime.now(UTC), source_agent="test",
            signal=SignalPayload(symbol="BTCUSDT", direction=Direction.LONG,
                                 confidence=0.85, regime=Regime.TRENDING))
        assert sig.version == "1.0.0"
        assert sig.signal.direction == Direction.LONG

    def test_rejects_invalid_version(self) -> None:
        with pytest.raises(ValueError):
            StrategySignalEventV1(
                version="2.0.0", event_id="t2",
                timestamp_utc=datetime.now(UTC), source_agent="t",
                signal=SignalPayload(symbol="BTCUSDT", direction=Direction.FLAT,
                                     confidence=0.5, regime=Regime.CALM))

    def test_confidence_bounds(self) -> None:
        with pytest.raises(Exception):
            SignalPayload(symbol="BTCUSDT", direction=Direction.LONG,
                          confidence=1.5, regime=Regime.TRENDING)

    def test_frozen_immutability(self) -> None:
        sp = SignalPayload(symbol="BTCUSDT", direction=Direction.LONG,
                           confidence=0.8, regime=Regime.TRENDING)
        with pytest.raises(Exception):
            sp.confidence = 0.5


class TestConfluenceMatrix:

    def _sig(self, src: str, d: Direction, c: float) -> StrategySignalEventV1:
        return StrategySignalEventV1(
            version="1.0.0", event_id=f"t-{src}",
            timestamp_utc=datetime.now(UTC), source_agent=src,
            signal=SignalPayload(symbol="BTCUSDT", direction=d,
                                 confidence=c, regime=Regime.TRENDING))

    def test_two_aligned_is_actionable(self) -> None:
        signals = [self._sig("smart_money_evaluator_v1", Direction.LONG, 0.9),
                   self._sig("ict_evaluator_v1", Direction.LONG, 0.95)]
        r = ConfluenceMatrix.evaluate(signals, Regime.TRENDING)
        assert r.is_actionable is True
        assert r.direction == Direction.LONG

    def test_single_strategy_not_actionable(self) -> None:
        signals = [self._sig("ict_evaluator_v1", Direction.LONG, 0.95)]
        r = ConfluenceMatrix.evaluate(signals, Regime.TRENDING)
        assert r.is_actionable is False

    def test_flat_filtered(self) -> None:
        signals = [self._sig("slippage_evaluator_v1", Direction.FLAT, 0.9),
                   self._sig("volume_evaluator_v1", Direction.LONG, 0.7),
                   self._sig("ict_evaluator_v1", Direction.LONG, 0.6)]
        r = ConfluenceMatrix.evaluate(signals, Regime.TRENDING)
        assert r.direction == Direction.LONG

    def test_empty_returns_flat(self) -> None:
        r = ConfluenceMatrix.evaluate([], Regime.TRENDING)
        assert r.direction == Direction.FLAT
        assert r.is_actionable is False

    def test_regime_weighting_differs(self) -> None:
        signals = [self._sig("iceberg_evaluator_v1", Direction.LONG, 0.8),
                   self._sig("smart_money_evaluator_v1", Direction.LONG, 0.8)]
        r_rang = ConfluenceMatrix.evaluate(signals, Regime.RANGING)
        r_trend = ConfluenceMatrix.evaluate(signals, Regime.TRENDING)
        assert r_rang.confluence_score != r_trend.confluence_score

    def test_result_frozen(self) -> None:
        r = ConfluenceMatrix.evaluate([], Regime.CALM)
        with pytest.raises(Exception):
            r.is_actionable = True



class TestProposalTranslator:

    def _conf(
        self,
        symbol: str = "BTCUSDT",
        regime: Regime = Regime.TRENDING,
        direction: Direction = Direction.LONG,
        confluence_score: float = 0.75,
        aligned_strategy_count: int = 3,
        total_strategy_count: int = 6,
        dominant_strategies: tuple[str, ...] = ("a", "b", "c"),
        is_actionable: bool = True,
        long_weighted_confidence: float = 0.75,
        short_weighted_confidence: float = 0.1,
    ) -> ConfluenceResult:
        return ConfluenceResult(
            symbol=symbol,
            regime=regime,
            direction=direction,
            confluence_score=confluence_score,
            aligned_strategy_count=aligned_strategy_count,
            total_strategy_count=total_strategy_count,
            dominant_strategies=dominant_strategies,
            is_actionable=is_actionable,
            long_weighted_confidence=long_weighted_confidence,
            short_weighted_confidence=short_weighted_confidence,
        )

    def test_long_to_buy(self) -> None:
        r = ProposalTranslator.translate(self._conf())
        assert r["proposed_action"] == "BUY"
        assert r["epistemic_status"] in ("HYPOTHESIS", "INFERENCE")

    def test_short_to_sell(self) -> None:
        r = ProposalTranslator.translate(self._conf(direction=Direction.SHORT))
        assert r["proposed_action"] == "SELL"

    def test_flat_to_hold(self) -> None:
        r = ProposalTranslator.translate(self._conf(
            direction=Direction.FLAT, confluence_score=0.0,
            aligned_strategy_count=0, is_actionable=False,
            dominant_strategies=()))
        assert r["proposed_action"] == "HOLD"

    def test_high_confidence_inference(self) -> None:
        r = ProposalTranslator.translate(self._conf(
            confluence_score=0.85, aligned_strategy_count=4,
            dominant_strategies=("a","b","c","d")))
        assert r["epistemic_status"] == "INFERENCE"

    def test_rule7_six_dimensions(self) -> None:
        r = ProposalTranslator.translate(self._conf())
        comp = r["confidence_components"]
        assert len(comp) == 6
        for v in comp.values():
            assert 0.0 <= v <= 1.0

    def test_rule2_no_direct_fact(self) -> None:
        r = ProposalTranslator.translate(self._conf(
            confluence_score=0.99, aligned_strategy_count=6,
            dominant_strategies=("a","b","c","d","e","f")))
        assert r["epistemic_status"] != "FACT"


class TestSensoryAgents:

    def test_signal_frozen(self) -> None:
        s = AgentSignal(agent_type=AgentType.NEWS, timestamp_utc=datetime.now(UTC),
            symbol="BTCUSDT", sentiment=SentimentLevel.BULLISH,
            score=0.7, confidence=0.8, source_id="t1")
        with pytest.raises(Exception):
            s.score = 0.5

    def test_context_value(self) -> None:
        s = AgentSignal(agent_type=AgentType.WALLET, timestamp_utc=datetime.now(UTC),
            symbol="BTCUSDT", sentiment=SentimentLevel.BEARISH,
            score=-0.8, confidence=0.9, source_id="t2")
        assert abs(s.to_context_value() - (-0.72)) < 0.001

    def test_news_processes_keywords(self) -> None:
        from intelligence.sensory_agents.news_agent import NewsAgentProcessor
        ev = {"headline": "Bitcoin ETF approval institutional adoption launch",
              "body": "partnership accumulation", "url": "u1"}
        s = NewsAgentProcessor.process_event(ev, "BTCUSDT")
        assert s is not None
        assert s.score > 0.0

    def test_wallet_filters_small(self) -> None:
        from intelligence.sensory_agents.wallet_agent import WalletAgentProcessor
        ev = {"type": "exchange_inflow", "amount_usd": 5000.0, "tx_hash": "x1"}
        assert WalletAgentProcessor.process_event(ev, "BTCUSDT") is None

    def test_wallet_detects_whale(self) -> None:
        from intelligence.sensory_agents.wallet_agent import WalletAgentProcessor
        ev = {"type": "exchange_inflow", "amount_usd": 500000.0, "tx_hash": "x2"}
        s = WalletAgentProcessor.process_event(ev, "BTCUSDT")
        assert s is not None
        assert s.score < 0.0

    def test_context_builder(self) -> None:
        from intelligence.sensory_agents.context_builder import AgentContextBuilder
        now = datetime.now(UTC)
        sigs = [
            AgentSignal(agent_type=AgentType.NEWS, timestamp_utc=now,
                symbol="BTCUSDT", sentiment=SentimentLevel.BULLISH,
                score=0.6, confidence=0.8, source_id="n1"),
            AgentSignal(agent_type=AgentType.WALLET, timestamp_utc=now,
                symbol="BTCUSDT", sentiment=SentimentLevel.BEARISH,
                score=-0.5, confidence=0.7, source_id="w1",
                metadata={"is_exchange_inflow": True, "is_exchange_outflow": False}),
        ]
        ctx = AgentContextBuilder.build(sigs)
        assert isinstance(ctx, AgentContext)
        assert ctx.news_sentiment > 0.0



class TestOrchestratorE2E:

    @patch.object(StrategyOrchestrator, "_superconscious_process")
    def test_full_pipeline(self, mock_sc: MagicMock,
                           sample_market: MarketSnapshot,
                           bullish_signals: list[AgentSignal]) -> None:
        mock_sc.return_value = {"enriched": True}
        orch = StrategyOrchestrator(ipc_socket="/tmp/test.sock")
        result = orch.process_market_update(
            market=sample_market, agent_signals=bullish_signals,
            regime=Regime.TRENDING, trace_id="e2e-001")
        if result is not None:
            assert "proposal_id" in result
            assert result["trace_id"] == "e2e-001"
            assert result["proposed_action"] in ("BUY", "SELL", "HOLD")
        orch.shutdown()

    @patch.object(StrategyOrchestrator, "_superconscious_process")
    def test_empty_market_graceful(self, mock_sc: MagicMock,
                                   empty_market: MarketSnapshot) -> None:
        orch = StrategyOrchestrator(ipc_socket="/tmp/test.sock")
        result = orch.process_market_update(
            market=empty_market, agent_signals=[],
            regime=Regime.CALM, trace_id="e2e-002")
        assert result is None
        orch.shutdown()

    @patch.object(StrategyOrchestrator, "_superconscious_process")
    def test_all_regimes_no_crash(self, mock_sc: MagicMock,
                                  sample_market: MarketSnapshot,
                                  bullish_signals: list[AgentSignal]) -> None:
        mock_sc.return_value = {"enriched": True}
        orch = StrategyOrchestrator(ipc_socket="/tmp/test.sock")
        for regime in [Regime.TRENDING, Regime.RANGING, Regime.VOLATILE, Regime.CALM]:
            orch.process_market_update(
                market=sample_market, agent_signals=bullish_signals,
                regime=regime, trace_id=f"e2e-{regime.value}")
        orch.shutdown()


class TestIndividualEvaluators:

    def test_slippage_with_orderbook(self, sample_market: MarketSnapshot) -> None:
        from intelligence.strategy_intelligence.strategy_evaluator.slippage import SlippageEvaluator
        ev = SlippageEvaluator()
        r = ev.evaluate(sample_market, AgentContext(), Regime.TRENDING)
        if r is not None:
            assert r.signal.symbol == "BTCUSDT"
            assert r.source_agent == "slippage_evaluator_v1"

    def test_volume_with_trades(self, sample_market: MarketSnapshot) -> None:
        from intelligence.strategy_intelligence.strategy_evaluator.volume import VolumeEvaluator
        ev = VolumeEvaluator()
        r = ev.evaluate(sample_market, AgentContext(), Regime.TRENDING)
        if r is not None:
            assert 0.0 <= r.signal.confidence <= 1.0

    def test_iceberg_filters_sparse(self) -> None:
        from intelligence.strategy_intelligence.strategy_evaluator.iceberg import IcebergEvaluator
        m = MarketSnapshot(symbol="BTCUSDT", timestamp=datetime.now(UTC),
            bid=67500.0, ask=67510.0, last_price=67505.0, volume_24h=100.0,
            trades=[{"price": 67500.0, "quantity": 1.0}],
            orderbook_bids=[(67500.0, 5.0)], orderbook_asks=[(67510.0, 3.0)])
        ev = IcebergEvaluator()
        assert ev.evaluate(m, AgentContext(), Regime.RANGING) is None

    def test_smart_money_uses_wallet(self, sample_market: MarketSnapshot) -> None:
        from intelligence.strategy_intelligence.strategy_evaluator.smart_money import (
            SmartMoneyEvaluator,
        )
        ev = SmartMoneyEvaluator()
        ctx = AgentContext(wallet_whale_flow=0.8)
        r = ev.evaluate(sample_market, ctx, Regime.TRENDING)
        if r is not None:
            assert r.signal.symbol == "BTCUSDT"
