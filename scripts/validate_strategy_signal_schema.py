"""Validate strategy-signal-event-v1 legacy boundary schema against draft-07.

Schema: contracts/schemas/strategy/strategy-signal-event-v1.schema.json
Policy: governance/policies/python-policy.yaml
"""
import json
from pathlib import Path
from jsonschema import Draft7Validator

SCHEMA_PATH = Path("contracts/schemas/strategy/strategy-signal-event-v1.schema.json")

def validate() -> None:
    raw = SCHEMA_PATH.read_text(encoding="utf-8")
    schema = json.loads(raw)
    Draft7Validator.check_schema(schema)
    sample = {
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
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(sample))
    if errors:
        raise AssertionError(f"Sample validation failed: {errors}")
    print("✅  strategy-signal-event-v1 boundary schema is valid and sample passes.")

if __name__ == "__main__":
    validate()
