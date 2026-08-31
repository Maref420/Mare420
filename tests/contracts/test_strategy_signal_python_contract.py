"""Contract tests for StrategySignalEventV1 Python adapter.

Validates that the Python adapter matches Rust contract_types.rs behavior.
Schema: contracts/schemas/strategy/strategy-signal-event-v1.schema.json
Policy: governance/policies/python-policy.yaml
"""
from __future__ import annotations

import json

import pytest

from intelligence.strategy_intelligence.contract_adapter import (
    ContractValidationError,
    StrategySignalEventV1,
)

SAMPLE_JSON = json.dumps({
    "version": "1.0.0",
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp_utc": "2026-08-31T10:00:00Z",
    "source_agent": "strategy_selector_v2",
    "signal": {
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "confidence": 0.87,
        "regime": "TRENDING",
    },
})


def test_deserialize_sample():
    event = StrategySignalEventV1.from_json(SAMPLE_JSON)
    assert event.version == "1.0.0"
    assert event.signal.direction == "LONG"
    assert event.signal.regime == "TRENDING"
    assert abs(event.signal.confidence - 0.87) < 1e-9


def test_roundtrip_serialization():
    original = StrategySignalEventV1.from_json(SAMPLE_JSON)
    restored = StrategySignalEventV1.from_json(original.to_json())
    assert original == restored


def test_create_factory():
    event = StrategySignalEventV1.create(
        source_agent="test_agent",
        symbol="ETHUSDT",
        direction="SHORT",
        confidence=0.65,
        regime="RANGING",
    )
    assert event.version == "1.0.0"
    assert event.signal.direction == "SHORT"
    assert event.source_agent == "test_agent"
    restored = StrategySignalEventV1.from_json(event.to_json())
    assert event == restored


def test_empty_source_agent_rejected():
    data = json.loads(SAMPLE_JSON)
    data["source_agent"] = ""
    with pytest.raises(ContractValidationError, match="source_agent"):
        StrategySignalEventV1.from_json(json.dumps(data))


def test_invalid_version_rejected():
    data = json.loads(SAMPLE_JSON)
    data["version"] = "2.0.0"
    with pytest.raises(ContractValidationError, match="version"):
        StrategySignalEventV1.from_json(json.dumps(data))


def test_invalid_direction_rejected():
    data = json.loads(SAMPLE_JSON)
    data["signal"]["direction"] = "INVALID"
    with pytest.raises(ContractValidationError, match="direction"):
        StrategySignalEventV1.from_json(json.dumps(data))


def test_confidence_out_of_range_rejected():
    data = json.loads(SAMPLE_JSON)
    data["signal"]["confidence"] = 1.5
    with pytest.raises(ContractValidationError, match="confidence"):
        StrategySignalEventV1.from_json(json.dumps(data))


def test_invalid_symbol_rejected():
    data = json.loads(SAMPLE_JSON)
    data["signal"]["symbol"] = "x"
    with pytest.raises(ContractValidationError, match="symbol"):
        StrategySignalEventV1.from_json(json.dumps(data))


def test_unknown_fields_rejected():
    data = json.loads(SAMPLE_JSON)
    data["unexpected_field"] = True
    with pytest.raises(ContractValidationError, match="unknown fields"):
        StrategySignalEventV1.from_json(json.dumps(data))
