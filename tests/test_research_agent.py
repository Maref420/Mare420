# MODULE: atlas-research-agent
# TEST TYPE: Unit tests
from __future__ import annotations

import json
import time

import pytest

from intelligence.research_agent.agent import ResearchAgent
from intelligence.research_agent.models import (
    AppError,
    ExperimentResult,
    ForensicsSignal,
    PatternRecord,
)


def _sig(**overrides: object) -> ForensicsSignal:
    defaults = dict(
        symbol="BTCUSDT", raw_spread_bps=10, aqs_score=50,
        confidence=0.7, orderbook_imbalance=0.2, vpin_toxicity=0.4,
        spoofing_detected=False, trace_id="t1",
        timestamp_ns=int(time.time_ns()),
        source_uri="rust-engine://v1",
    )
    defaults.update(overrides)
    return ForensicsSignal.model_validate(defaults)


@pytest.fixture
def agent() -> ResearchAgent:
    return ResearchAgent({"aqs_threshold": 50, "toxicity_threshold": 0.5})


def test_high_aqs_low_toxicity_investigate(agent: ResearchAgent) -> None:
    sig = _sig(aqs_score=80, vpin_toxicity=0.2)
    d = agent.process_signal(json.dumps(sig.model_dump()), "t1")
    assert d.action == "investigate"
    assert d.confidence > 0.5


def test_spoofing_detected_alert(agent: ResearchAgent) -> None:
    sig = _sig(spoofing_detected=True)
    d = agent.process_signal(json.dumps(sig.model_dump()), "t2")
    assert d.action == "alert"
    assert d.confidence == 0.95


def test_low_aqs_ignore(agent: ResearchAgent) -> None:
    sig = _sig(aqs_score=20)
    d = agent.process_signal(json.dumps(sig.model_dump()), "t3")
    assert d.action == "ignore"


def test_medium_aqs_archive(agent: ResearchAgent) -> None:
    sig = _sig(aqs_score=40, vpin_toxicity=0.6)
    d = agent.process_signal(json.dumps(sig.model_dump()), "t4")
    assert d.action == "archive"


def test_learning_boosts_confidence(agent: ResearchAgent) -> None:
    pattern = PatternRecord(
        pattern_id="p1", symbol="BTCUSDT",
        conditions={"min_aqs": 40, "max_toxicity": 0.5, "no_spoofing": True, "min_imbalance": 0.1},
        win_rate=0.8, sample_count=5,
        last_seen_ms=int(time.time() * 1000),
        source_uri="test://patterns",
    )
    agent.learning.register_pattern(pattern)
    sig = _sig(aqs_score=50, vpin_toxicity=0.4)
    d = agent.process_signal(json.dumps(sig.model_dump()), "t5")
    assert d.confidence > 0.7


def test_confidence_capped_at_1_0(agent: ResearchAgent) -> None:
    pattern = PatternRecord(
        pattern_id="p2", symbol="BTCUSDT",
        conditions={"min_aqs": 70, "max_toxicity": 0.3, "no_spoofing": True},
        win_rate=0.9, sample_count=5,
        last_seen_ms=int(time.time() * 1000),
        source_uri="test://patterns",
    )
    agent.learning.register_pattern(pattern)
    sig = _sig(aqs_score=75, confidence=0.95, vpin_toxicity=0.2)
    d = agent.process_signal(json.dumps(sig.model_dump()), "t6")
    assert d.confidence == 1.0


def test_record_experiment_updates_win_rate(agent: ResearchAgent) -> None:
    pattern = PatternRecord(
        pattern_id="p3", symbol="BTCUSDT", conditions={},
        win_rate=0.5, sample_count=10,
        last_seen_ms=int(time.time() * 1000),
        source_uri="test://patterns",
    )
    agent.learning.register_pattern(pattern)
    result = ExperimentResult(
        experiment_id="e1", pattern_id="p3", outcome="win",
        pnl_scaled=100, details="test",
        timestamp_ms=int(time.time() * 1000),
    )
    agent.learn_from_outcome(result)
    updated = agent.learning._patterns["p3"]
    expected = (0.5 * 10 + 1.0) / 11.0
    assert abs(updated.win_rate - expected) < 0.001


def test_get_top_patterns_sorted(agent: ResearchAgent) -> None:
    ts = int(time.time() * 1000)
    agent.learning.register_pattern(PatternRecord(pattern_id="a", symbol="X", conditions={}, win_rate=0.7, sample_count=10, last_seen_ms=ts, source_uri="u"))
    agent.learning.register_pattern(PatternRecord(pattern_id="b", symbol="X", conditions={}, win_rate=0.9, sample_count=5, last_seen_ms=ts, source_uri="u"))
    agent.learning.register_pattern(PatternRecord(pattern_id="c", symbol="X", conditions={}, win_rate=0.8, sample_count=8, last_seen_ms=ts, source_uri="u"))
    top = agent.learning.get_top_patterns(limit=2)
    assert top[0].pattern_id == "b"
    assert top[1].pattern_id == "c"


def test_invalid_json_raises_error(agent: ResearchAgent) -> None:
    with pytest.raises(AppError) as exc:
        agent.process_signal("{bad", "t7")
    assert exc.value.code == "VAL_INVALID_JSON"


def test_missing_source_uri_raises_error(agent: ResearchAgent) -> None:
    payload = dict(
        symbol="BTCUSDT", raw_spread_bps=10, aqs_score=50,
        confidence=0.7, orderbook_imbalance=0.2, vpin_toxicity=0.4,
        spoofing_detected=False, trace_id="t8",
        timestamp_ns=int(time.time_ns()), source_uri="",
    )
    with pytest.raises(AppError) as exc:
        agent.process_signal(json.dumps(payload), "t8")
    assert "VAL_" in exc.value.code


def test_health_check(agent: ResearchAgent) -> None:
    h = agent.health_check()
    assert h["status"] == "healthy"
    assert h["agent_id"] == "research_agent"


def test_models_frozen(agent: ResearchAgent) -> None:
    sig = _sig()
    with pytest.raises(Exception):
        sig.symbol = "ETH"  # type: ignore[misc]
