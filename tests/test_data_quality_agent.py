# MODULE: atlas-data-quality-agent
# TEST TYPE: Unit tests for DataQualityAgent
import json
import time

import pytest

from intelligence.data_quality_agent.agent import DataQualityAgent
from intelligence.data_quality_agent.anomaly import AnomalyDetector
from intelligence.data_quality_agent.models import (
    AnomalyAlert,
    AppError,
    SpreadSignal,
    ValidationReport,
)

SAMPLE_CONFIG = {
    "spread_threshold_bps": 50,
    "stale_threshold_ms": 5000,
    "min_sources": 2,
}


@pytest.fixture
def agent() -> DataQualityAgent:
    return DataQualityAgent(config=SAMPLE_CONFIG)


@pytest.fixture
def valid_signal_payload() -> str:
    return json.dumps({
        "symbol": "BTCUSDT",
        "buy_exchange": "bybit",
        "sell_exchange": "okx",
        "buy_price_scaled": 65000000000,
        "sell_price_scaled": 65001000000,
        "spread_bps": 15,
        "timestamp_ns": int(time.time() * 1e9),
        "source_uri": "cross-validator://v1/BTCUSDT",
    })


@pytest.fixture
def stale_signal_payload() -> str:
    old_ts = int((time.time() - 10) * 1e9)
    return json.dumps({
        "symbol": "ETHUSDT",
        "buy_exchange": "aster",
        "sell_exchange": "hyperliquid",
        "buy_price_scaled": 3000000000,
        "sell_price_scaled": 3000100000,
        "spread_bps": 5,
        "timestamp_ns": old_ts,
        "source_uri": "cross-validator://v1/ETHUSDT",
    })


def test_spread_within_threshold_no_alert(agent: DataQualityAgent, valid_signal_payload: str) -> None:
    alerts = agent.process_signal(valid_signal_payload, trace_id="test-1")
    assert len(alerts) == 0


def test_spread_exceeds_threshold_generates_alert(agent: DataQualityAgent, valid_signal_payload: str) -> None:
    payload = json.loads(valid_signal_payload)
    payload["spread_bps"] = 60
    alerts = agent.process_signal(json.dumps(payload), trace_id="test-2")
    assert len(alerts) == 1
    assert alerts[0].severity == "warning"
    assert alerts[0].issue == "spread_anomaly"


def test_critical_spread_above_200bps(agent: DataQualityAgent, valid_signal_payload: str) -> None:
    payload = json.loads(valid_signal_payload)
    payload["spread_bps"] = 250
    alerts = agent.process_signal(json.dumps(payload), trace_id="test-3")
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"


def test_stale_data_detection(agent: DataQualityAgent, stale_signal_payload: str) -> None:
    alerts = agent.process_signal(stale_signal_payload, trace_id="test-4")
    assert any(a.issue == "stale_data" for a in alerts)


def test_missing_sources_detection() -> None:
    detector = AnomalyDetector(min_sources=2)
    report = ValidationReport(
        symbol="BTCUSDT",
        source_count=1,
        median_price_scaled=65000000000,
        spread_bps=10,
        anomalous_exchanges=[],
        is_valid=True,
        timestamp_ms=int(time.time() * 1000),
    )
    alerts = detector.evaluate(report, trace_id="test-5")
    assert any(a.issue == "missing_sources" for a in alerts)


def test_process_signal_valid_json(agent: DataQualityAgent, valid_signal_payload: str) -> None:
    alerts = agent.process_signal(valid_signal_payload, trace_id="test-6")
    assert isinstance(alerts, list)


def test_process_signal_invalid_json_raises_app_error(agent: DataQualityAgent) -> None:
    with pytest.raises(AppError) as exc_info:
        agent.process_signal("{invalid json", trace_id="test-7")
    assert exc_info.value.code == "VAL_INVALID_JSON"
    assert exc_info.value.retryable is False


def test_health_check_returns_ok(agent: DataQualityAgent) -> None:
    health = agent.health_check()
    assert health["status"] == "healthy"
    assert health["liveness"] is True
    assert health["readiness"] is True


def test_models_frozen_immutable() -> None:
    sig = SpreadSignal(
        symbol="BTC",
        buy_exchange="bybit",
        sell_exchange="okx",
        buy_price_scaled=65000,
        sell_price_scaled=65001,
        spread_bps=15,
        timestamp_ns=int(time.time() * 1e9),
        source_uri="test://v1",
    )
    with pytest.raises(Exception):
        sig.symbol = "ETH"  # type: ignore[misc]

    alert = AnomalyAlert(
        severity="warning",
        symbol="BTC",
        exchange="bybit",
        issue="test",
        details="immutable",
        trace_id="tid",
        timestamp_ms=int(time.time() * 1000),
    )
    with pytest.raises(Exception):
        alert.severity = "critical"  # type: ignore[misc]
