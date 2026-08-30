"""Production-grade contract tests for Python strategy signal adapter.

Mirrors Rust contract_types tests to ensure cross-language parity.
"""

import json
import pytest

from intelligence.strategy_intelligence.contract_adapter import (
    ContractValidationError,
    Signal,
    StrategySignalEventV1,
)

SAMPLE_JSON = json.dumps({
    "version": "1.0.0",
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp_utc": "2026-08-31T10:00:00Z",
    "trace_id": "660e8400-e29b-41d4-a716-446655440001",
    "source_agent": "strategy_selector_v2",
    "signal": {
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "confidence": 0.87,
        "regime": "TRENDING",
    },
})


def test_deserialize_sample_payload():
    event = StrategySignalEventV1.from_json(SAMPLE_JSON)
    assert event.version == "1.0.0"
    assert event.signal.direction == "LONG"
    assert event.signal.regime == "TRENDING"
    assert abs(event.signal.confidence - 0.87) < 1e-9


def test_roundtrip_serialization():
    original = StrategySignalEventV1.from_json(SAMPLE_JSON)
    restored = StrategySignalEventV1.from_json(original.to_json())
    assert original == restored


def test_validate_valid_event():
    event = StrategySignalEventV1.from_json(SAMPLE_JSON)
    event.validate()  # Should not raise


def test_validate_invalid_version():
    data = json.loads(SAMPLE_JSON)
    data["version"] = "2.0.0"
    with pytest.raises(ContractValidationError, match="version"):
        StrategySignalEventV1.from_json(json.dumps(data))


def test_validate_invalid_symbol():
    data = json.loads(SAMPLE_JSON)
    data["signal"]["symbol"] = "x"
    with pytest.raises(ContractValidationError, match="symbol"):
        StrategySignalEventV1.from_json(json.dumps(data))


def test_validate_confidence_out_of_range():
    data = json.loads(SAMPLE_JSON)
    data["signal"]["confidence"] = 1.5
    with pytest.raises(ContractValidationError, match="confidence"):
        StrategySignalEventV1.from_json(json.dumps(data))


def test_deny_unknown_fields():
    data = json.loads(SAMPLE_JSON)
    data["unexpected_field"] = True
    with pytest.raises(ContractValidationError, match="unknown fields"):
        StrategySignalEventV1.from_json(json.dumps(data))


def test_deny_unknown_signal_fields():
    data = json.loads(SAMPLE_JSON)
    data["signal"]["extra"] = "bad"
    with pytest.raises(ContractValidationError, match="unknown signal fields"):
        StrategySignalEventV1.from_json(json.dumps(data))


def test_create_factory_method():
    event = StrategySignalEventV1.create(
        source_agent="test_agent",
        symbol="ETHUSDT",
        direction="SHORT",
        confidence=0.72,
        regime="VOLATILE",
    )
    assert event.version == "1.0.0"
    assert event.signal.symbol == "ETHUSDT"
    assert event.signal.direction == "SHORT"
    # Verify it round-trips
    restored = StrategySignalEventV1.from_json(event.to_json())
    assert event == restored


def test_empty_source_agent_rejected():
    data = json.loads(SAMPLE_JSON)
    data["source_agent"] = ""
    with pytest.raises(ContractValidationError, match="source_agent"):
        StrategySignalEventV1.from_json(json.dumps(data))


def test_invalid_direction_rejected():
    data = json.loads(SAMPLE_JSON)
    data["signal"]["direction"] = "INVALID"
    with pytest.raises(ContractValidationError, match="direction"):
        StrategySignalEventV1.from_json(json.dumps(data))
