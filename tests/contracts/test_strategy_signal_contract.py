"""Production-grade contract tests for strategy-signal-event-v1."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pytest
from jsonschema import Draft7Validator, ValidationError

SCHEMA_PATH = Path("contracts/schemas/strategy/strategy-signal-event-v1.schema.json")

@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

@pytest.fixture(scope="module")
def validator(schema):
    return Draft7Validator(schema)

def _valid_signal(**overrides):
    """Return a valid signal object with optional overrides."""
    base = {
        "symbol": "ETHUSDT",
        "direction": "SHORT",
        "confidence": 0.72,
        "regime": "VOLATILE"
    }
    base.update(overrides)
    return base

def _valid_event(**overrides):
    base = {
        "version": "1.0.0",
        "event_id": str(uuid.uuid4()),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "trace_id": str(uuid.uuid4()),
        "source_agent": "test_agent",
        "signal": _valid_signal()
    }
    base.update(overrides)
    return base

def test_valid_event_passes(validator):
    validator.validate(_valid_event())

def test_missing_required_field_fails(validator):
    event = _valid_event()
    del event["signal"]["confidence"]
    with pytest.raises(ValidationError, match="confidence"):
        validator.validate(event)

def test_invalid_direction_enum_fails(validator):
    event = _valid_event(signal=_valid_signal(direction="INVALID"))
    errors = list(validator.iter_errors(event))
    assert len(errors) == 1
    assert "INVALID" in errors[0].message

def test_confidence_out_of_range_fails(validator):
    event = _valid_event(signal=_valid_signal(confidence=1.5))
    errors = list(validator.iter_errors(event))
    assert len(errors) == 1
    assert "1.5" in errors[0].message

def test_additional_properties_rejected(validator):
    event = _valid_event()
    event["unexpected_field"] = "should_fail"
    with pytest.raises(ValidationError, match="Additional properties"):
        validator.validate(event)

def test_symbol_pattern_enforced(validator):
    """Symbol must match ^[A-Z0-9]{2,20}$ — lowercase single char fails."""
    event = _valid_event(signal=_valid_signal(symbol="x"))
    errors = list(validator.iter_errors(event))
    assert len(errors) == 1
    assert "does not match" in errors[0].message
    assert "^[A-Z0-9]{2,20}$" in errors[0].message

def test_multiple_violations_reported(validator):
    event = _valid_event(signal=_valid_signal(
        symbol="x",
        direction="INVALID",
        confidence=2.0
    ))
    errors = list(validator.iter_errors(event))
    assert len(errors) >= 3
