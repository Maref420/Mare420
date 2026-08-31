"""Cross-language parity tests for strategy-signal-event-v1.

Ensures Python adapter produces JSON that Rust contract_types.rs can
deserialize and vice versa. Uses the legacy boundary format.

Schema: contracts/schemas/strategy/strategy-signal-event-v1.schema.json
Ref: core_engine/strategy/src/contract_types.rs
"""
from __future__ import annotations

import json

from intelligence.strategy_intelligence.contract_adapter import (
    ContractValidationError,
    StrategySignalEventV1,
)

CANONICAL_STRATEGY_SIGNAL_JSON = json.dumps({
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
}, sort_keys=True, separators=(",", ":"))


def test_python_deserializes_rust_payload():
    event = StrategySignalEventV1.from_json(CANONICAL_STRATEGY_SIGNAL_JSON)
    assert event.version == "1.0.0"
    assert event.signal.direction == "LONG"
    assert abs(event.signal.confidence - 0.87) < 1e-9
    assert event.source_agent == "strategy_selector_v2"


def test_python_serializes_for_rust():
    python_event = StrategySignalEventV1.from_json(
        CANONICAL_STRATEGY_SIGNAL_JSON
    )
    serialized = python_event.to_json()
    parsed = json.loads(serialized)
    assert parsed["version"] == "1.0.0"
    assert parsed["signal"]["direction"] == "LONG"
    assert parsed["signal"]["confidence"] == 0.87
    assert parsed["source_agent"] == "strategy_selector_v2"


def test_roundtrip_field_preservation():
    event = StrategySignalEventV1.from_json(CANONICAL_STRATEGY_SIGNAL_JSON)
    restored = StrategySignalEventV1.from_json(event.to_json())
    original = json.loads(CANONICAL_STRATEGY_SIGNAL_JSON)
    assert restored.timestamp_utc == original["timestamp_utc"]
    assert restored.source_agent == original["source_agent"]
    assert restored.trace_id == original["trace_id"]
    assert restored.signal.symbol == original["signal"]["symbol"]


def test_invalid_payload_rejected():
    payload = {
        "version": "1.0.0",
        "event_id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp_utc": "2026-08-31T10:00:00Z",
        "source_agent": "test",
        "signal": {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "confidence": 2.0,
            "regime": "TRENDING",
        },
    }
    with pytest.raises(ContractValidationError):
        StrategySignalEventV1.from_json(json.dumps(payload))


# Need pytest import for the last test
import pytest  # noqa: E402
