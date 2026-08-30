"""Strategy Signal Event v1 — Contract Boundary Adapter.

Stdlib-only implementation. No external dependencies.
Schema: contracts/schemas/strategy/strategy-signal-event-v1.schema.json
Policy: governance/policies/python-policy.yaml

This module is the Python-side counterpart of Rust's contract_types.rs.
Both enforce identical validation rules against the same JSON Schema.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{2,20}$")
_VALID_DIRECTIONS = frozenset({"LONG", "SHORT", "FLAT"})
_VALID_REGIMES = frozenset({"TRENDING", "RANGING", "VOLATILE", "CALM"})
_REQUIRED_VERSION = "1.0.0"


class ContractValidationError(ValueError):
    """Raised when a strategy signal event violates schema constraints."""


@dataclass(frozen=True)
class Signal:
    """Inner signal payload matching schema's signal object."""

    symbol: str
    direction: str
    confidence: float
    regime: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not _SYMBOL_PATTERN.match(self.symbol):
            raise ContractValidationError(
                f"symbol '{self.symbol}' does not match ^[A-Z0-9]{{2,20}}$"
            )
        if self.direction not in _VALID_DIRECTIONS:
            raise ContractValidationError(
                f"direction '{self.direction}' not in {_VALID_DIRECTIONS}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ContractValidationError(
                f"confidence {self.confidence} out of range [0.0, 1.0]"
            )
        if self.regime not in _VALID_REGIMES:
            raise ContractValidationError(
                f"regime '{self.regime}' not in {_VALID_REGIMES}"
            )


@dataclass(frozen=True)
class StrategySignalEventV1:
    """Top-level event envelope matching strategy-signal-event-v1 schema.

    Frozen to enforce immutability after construction.
    Use from_json() for deserialization with validation.
    """

    version: str
    event_id: str
    timestamp_utc: str
    source_agent: str
    signal: Signal
    trace_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate all contract-boundary constraints."""
        if self.version != _REQUIRED_VERSION:
            raise ContractValidationError(
                f"version must be '{_REQUIRED_VERSION}', got '{self.version}'"
            )
        if not self.source_agent:
            raise ContractValidationError("source_agent must not be empty")
        # Validate UUID format
        try:
            uuid.UUID(self.event_id)
        except ValueError as exc:
            raise ContractValidationError(
                f"event_id is not a valid UUID: {exc}"
            ) from exc
        if self.trace_id is not None:
            try:
                uuid.UUID(self.trace_id)
            except ValueError as exc:
                raise ContractValidationError(
                    f"trace_id is not a valid UUID: {exc}"
                ) from exc
        self.signal.validate()

    def to_json(self) -> str:
        """Serialize to canonical JSON string. Validates before serialization.

        Canonical format: sorted keys, compact, deterministic.
        Matches Rust serde_json output for cross-language parity.
        """
        self.validate()
        data = asdict(self)
        # Remove None values for optional fields (absent from input)
        if data.get("trace_id") is None:
            del data["trace_id"]
        # Remove empty parameters/metadata dicts for canonical form
        if not data.get("signal", {}).get("parameters"):
            data.get("signal", {}).pop("parameters", None)
        if not data.get("metadata"):
            data.pop("metadata", None)
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> StrategySignalEventV1:
        """Deserialize from JSON string with full validation."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContractValidationError(f"invalid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ContractValidationError("expected JSON object")

        # Check for unknown top-level fields
        known_fields = {
            "version", "event_id", "timestamp_utc", "trace_id",
            "source_agent", "signal", "metadata",
        }
        unknown = set(data.keys()) - known_fields
        if unknown:
            raise ContractValidationError(
                f"unknown fields: {unknown}"
            )

        # Parse signal
        signal_data = data.get("signal")
        if not isinstance(signal_data, dict):
            raise ContractValidationError("signal must be an object")

        known_signal_fields = {
            "symbol", "direction", "confidence", "regime", "parameters",
        }
        unknown_signal = set(signal_data.keys()) - known_signal_fields
        if unknown_signal:
            raise ContractValidationError(
                f"unknown signal fields: {unknown_signal}"
            )

        signal = Signal(
            symbol=signal_data.get("symbol", ""),
            direction=signal_data.get("direction", ""),
            confidence=float(signal_data.get("confidence", -1)),
            regime=signal_data.get("regime", ""),
            parameters=signal_data.get("parameters", {}),
        )

        event = cls(
            version=data.get("version", ""),
            event_id=data.get("event_id", ""),
            timestamp_utc=data.get("timestamp_utc", ""),
            source_agent=data.get("source_agent", ""),
            signal=signal,
            trace_id=data.get("trace_id"),
            metadata=data.get("metadata", {}),
        )

        event.validate()
        return event

    @classmethod
    def create(
        cls,
        source_agent: str,
        symbol: str,
        direction: str,
        confidence: float,
        regime: str,
        parameters: dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StrategySignalEventV1:
        """Factory method with auto-generated event_id and timestamp."""
        event = cls(
            version=_REQUIRED_VERSION,
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            source_agent=source_agent,
            signal=Signal(
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                regime=regime,
                parameters=parameters or {},
            ),
            metadata=metadata or {},
        )
        event.validate()
        return event
