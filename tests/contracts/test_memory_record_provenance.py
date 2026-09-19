"""
Validation tests for Upgraded Memory Record Provenance.
Ensures backward compatibility while enforcing new governance rules.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from intelligence.contracts.unified_decision_proposal import (
    EpistemicStatus,
    FailureTaxonomy,
)
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)


def _build_base_payload() -> dict[str, Any]:
    """Minimal payload matching legacy instantiation patterns."""
    return {
        "memory_id": "mem-001",
        "memory_type": MemoryType.EPISODIC.value,
        "created_at": datetime.now(UTC).isoformat(),
        "content": {"strategy": "X", "outcome": "loss"},
        "metadata": {},
        "validation_status": ValidationStatus.PENDING.value,
        "operation_id": "op-001",
        "agent_id": "agent-001",
    }


def test_backward_compatibility_legacy_instantiation() -> None:
    """Ensure existing code (like experience_engine) doesn't break."""
    payload = _build_base_payload()
    record = MemoryRecord(**payload)

    assert record.memory_id == "mem-001"
    # Verify defaults are applied safely
    assert record.source == "UNKNOWN_SOURCE"
    assert record.epistemic_status == EpistemicStatus.UNKNOWN
    assert record.failure_taxonomy == FailureTaxonomy.NONE
    assert record.evidence_refs == []


def test_full_provenance_instantiation() -> None:
    """Verify new fields can be populated correctly."""
    payload = _build_base_payload()
    payload["source"] = "orderbook_feed"
    payload["source_type"] = "market_data"
    payload["regime"] = "high_volatility"
    payload["evidence_refs"] = ["ev-001", "ev-002"]
    payload["epistemic_status"] = EpistemicStatus.FACT.value
    payload["failure_taxonomy"] = FailureTaxonomy.F03_WRONG_EVIDENCE.value

    record = MemoryRecord(**payload)

    assert record.source == "orderbook_feed"
    assert record.regime == "high_volatility"
    assert len(record.evidence_refs) == 2
    assert record.epistemic_status == EpistemicStatus.FACT
    assert record.failure_taxonomy == FailureTaxonomy.F03_WRONG_EVIDENCE


def test_immutability_enforced_on_new_fields() -> None:
    """Rule 10: Contracts must be frozen after creation."""
    payload = _build_base_payload()
    record = MemoryRecord(**payload)

    with pytest.raises(ValidationError):
        record.regime = "new_regime"


def test_reject_extra_properties() -> None:
    """Ensure extra='forbid' is active."""
    payload = _build_base_payload()
    payload["unauthorized_field"] = "malicious_data"

    with pytest.raises(ValidationError):
        MemoryRecord(**payload)


def test_serialization_roundtrip_with_provenance() -> None:
    """Ensure JSON roundtrip preserves new fields."""
    payload = _build_base_payload()
    payload["source"] = "news_feed"
    payload["regime"] = "trending"
    payload["epistemic_status"] = EpistemicStatus.INFERENCE.value

    original = MemoryRecord(**payload)
    raw_json = original.to_json()
    restored = MemoryRecord.from_json(raw_json)

    assert original == restored
    assert restored.source == "news_feed"
    assert restored.epistemic_status == EpistemicStatus.INFERENCE
