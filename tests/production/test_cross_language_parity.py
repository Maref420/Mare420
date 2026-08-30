"""Cross-Language Parity Test for strategy-signal-event-v1.

Validates that Python and Rust implementations produce identical
serialization output from the same canonical input.

Governance: tests must pass before any integration wiring.
Schema: contracts/schemas/strategy/strategy-signal-event-v1.schema.json
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from intelligence.strategy_intelligence.contract_adapter import (
    StrategySignalEventV1,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL_FIXTURE = (
    PROJECT_ROOT / "tests" / "fixtures" / "strategy"
    / "strategy-signal-event-v1-canonical.json"
)


def _rust_serialize_canonical() -> str:
    """Run Rust parity_check binary to serialize canonical fixture.

    Returns the serialized JSON string from Rust's serde_json.
    """
    binary = PROJECT_ROOT / "core_engine" / "strategy" / "target" / "debug" / "parity_check"
    if not binary.exists():
        # Build the binary first
        subprocess.run(
            ["cargo", "build", "--bin", "parity_check"],
            cwd=PROJECT_ROOT / "core_engine" / "strategy",
            check=True,
            capture_output=True,
        )
    result = subprocess.run(
        [str(binary), str(CANONICAL_FIXTURE)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class TestCanonicalFixtureValidity:
    """Both languages must accept the canonical fixture without errors."""

    def test_python_accepts_canonical(self, canonical_strategy_signal_json: str):
        event = StrategySignalEventV1.from_json(canonical_strategy_signal_json)
        assert event.version == "1.0.0"
        assert event.signal.symbol == "BTCUSDT"

    def test_canonical_fixture_exists(self):
        assert CANONICAL_FIXTURE.exists(), (
            f"Canonical fixture missing: {CANONICAL_FIXTURE}"
        )

    def test_canonical_fixture_is_valid_json(self):
        raw = CANONICAL_FIXTURE.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert data["version"] == "1.0.0"


class TestSerializationParity:
    """Python and Rust must produce byte-identical serialization."""

    def test_roundtrip_hash_match(self, canonical_strategy_signal_json: str):
        """Deserialize in Python, re-serialize, compare hash with Rust."""
        # Python round-trip
        python_event = StrategySignalEventV1.from_json(
            canonical_strategy_signal_json
        )
        python_serialized = python_event.to_json()
        python_hash = hashlib.sha256(python_serialized.encode()).hexdigest()

        # Rust serialization
        rust_serialized = _rust_serialize_canonical()
        rust_hash = hashlib.sha256(rust_serialized.encode()).hexdigest()

        assert python_hash == rust_hash, (
            f"Serialization mismatch!\n"
            f"Python SHA256: {python_hash}\n"
            f"Rust   SHA256: {rust_hash}\n"
            f"Python output: {python_serialized[:200]}\n"
            f"Rust   output: {rust_serialized[:200]}"
        )

    def test_field_values_match_after_roundtrip(
        self, canonical_strategy_signal_json: str
    ):
        """After Python round-trip, all fields match original."""
        original = json.loads(canonical_strategy_signal_json)
        event = StrategySignalEventV1.from_json(canonical_strategy_signal_json)
        restored = json.loads(event.to_json())

        assert restored["version"] == original["version"]
        assert restored["event_id"] == original["event_id"]
        assert restored["timestamp_utc"] == original["timestamp_utc"]
        assert restored["source_agent"] == original["source_agent"]
        assert restored["signal"]["symbol"] == original["signal"]["symbol"]
        assert restored["signal"]["direction"] == original["signal"]["direction"]
        assert abs(
            restored["signal"]["confidence"] - original["signal"]["confidence"]
        ) < 1e-9
        assert restored["signal"]["regime"] == original["signal"]["regime"]


class TestRejectionParity:
    """Both languages must reject the same invalid payloads."""

    INVALID_PAYLOADS = [
        ("bad_version", {"version": "2.0.0"}),
        ("bad_symbol", {"signal": {"symbol": "x"}}),
        ("bad_confidence", {"signal": {"confidence": 1.5}}),
        ("bad_direction", {"signal": {"direction": "INVALID"}}),
        ("extra_field", {"unexpected": True}),
    ]

    @pytest.mark.parametrize("name,override", INVALID_PAYLOADS)
    def test_python_rejects_invalid(
        self,
        canonical_strategy_signal_dict: dict,
        name: str,
        override: dict,
    ):
        """Python must reject each invalid payload variant."""
        from intelligence.strategy_intelligence.contract_adapter import (
            ContractValidationError,
        )

        payload = json.loads(json.dumps(canonical_strategy_signal_dict))
        # Deep merge override
        for key, value in override.items():
            if isinstance(value, dict) and key in payload:
                payload[key].update(value)
            else:
                payload[key] = value

        with pytest.raises(ContractValidationError):
            StrategySignalEventV1.from_json(json.dumps(payload))
