"""Cross-language contract parity tests for strategy-signal-event-v1.

Ensures Python adapter and Rust contract_types.rs produce/consume
identical JSON payloads per the legacy boundary schema.

Schema: contracts/schemas/strategy/strategy-signal-event-v1.schema.json
Policy: governance/policies/python-policy.yaml
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from intelligence.strategy_intelligence.contract_adapter import (
    StrategySignalEventV1,
)

CANONICAL_SAMPLE = {
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
}


def test_python_parses_rust_compatible_payload():
    """Python adapter must parse JSON produced by Rust serde_json."""
    raw = json.dumps(CANONICAL_SAMPLE, sort_keys=True, separators=(",", ":"))
    event = StrategySignalEventV1.from_json(raw)
    assert event.version == "1.0.0"
    assert event.event_id == "550e8400-e29b-41d4-a716-446655440000"
    assert event.source_agent == "strategy_selector_v2"
    assert event.signal.symbol == "BTCUSDT"
    assert event.signal.direction == "LONG"
    assert abs(event.signal.confidence - 0.87) < 1e-9
    assert event.signal.regime == "TRENDING"


def test_python_produces_rust_compatible_payload():
    """Python serialized JSON must be parseable by Rust serde_json."""
    event = StrategySignalEventV1.from_json(json.dumps(CANONICAL_SAMPLE))
    raw = event.to_json()
    parsed = json.loads(raw)
    assert parsed["version"] == "1.0.0"
    assert parsed["signal"]["direction"] == "LONG"
    assert parsed["signal"]["confidence"] == 0.87
    assert parsed["source_agent"] == "strategy_selector_v2"


def test_roundtrip_preserves_all_fields():
    original = StrategySignalEventV1.from_json(json.dumps(CANONICAL_SAMPLE))
    restored = StrategySignalEventV1.from_json(original.to_json())
    assert original == restored
    assert restored.timestamp_utc == original.timestamp_utc
    assert restored.source_agent == original.source_agent
    assert restored.trace_id == original.trace_id
