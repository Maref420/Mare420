"""
Validation tests for Unified Decision Proposal Contract.
Ensures Anti-Hallucination rules and Governance boundaries are structurally enforced.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from intelligence.contracts.unified_decision_proposal import (
    AdversarialValidation,
    ConfidenceVector,
    ContradictionReport,
    DecisionProposal,
    EpistemicStatus,
    EvidenceRecord,
    ProposalStatus,
)


def _build_valid_proposal() -> dict[str, object]:
    """Helper to build a canonical valid proposal payload."""
    return {
        "proposal_id": "prop-001",
        "producer_agent_id": "market-agent-01",
        "agent_family": "INTELLIGENCE",
        "timestamp_ns": 1726800000000000000,
        "epistemic_status": EpistemicStatus.INFERENCE.value,
        "proposal_status": ProposalStatus.PROPOSAL.value,
        "target_strategy": "momentum_btc_v1",
        "proposed_action": "BUY_SIGNAL",
        "payload": {},
        "required_evidence": [
            {
                "evidence_id": "ev-001",
                "source": "orderbook_feed",
                "source_type": "market_data",
                "timestamp_ns": 1726800000000000000,
                "quality_score": 0.9,
                "reliability_score": 0.95,
                "cross_check_status": "VERIFIED",
            }
        ],
        "memory_provenance": [],
        "confidence_vector": {
            "evidence_quality": 0.9,
            "source_reliability": 0.9,
            "data_freshness": 0.9,
            "cross_validation": 0.8,
            "historical_accuracy": 0.85,
            "regime_compatibility": 0.9,
            "contradiction_level": 0.1,
            "adversarial_survival": 0.8,
            "risk_compatibility": 0.85,
        },
        "independent_validator_id": "validator-01",
        "adversarial_report": {
            "tested_by_agent": "adversarial-01",
            "overfitting_detected": False,
            "regime_failure_risk": 0.2,
            "data_leakage_risk": 0.05,
            "survival_score": 0.85,
        },
        "known_failures_from_memory": [],
        "contradiction_report": {
            "contradiction_detected": False,
            "conflicting_agents": [],
            "resolution_method": "none_required",
            "final_stance": "BULLISH",
        },
        "requires_human_approval": True,
        "audit_log_ref": "audit-ref-001",
    }


def test_valid_proposal_serialization_roundtrip() -> None:
    """Ensure JSON roundtrip matches legacy adapter behavior."""
    payload = _build_valid_proposal()
    proposal = DecisionProposal(**payload)

    raw_json = proposal.to_json()
    restored = DecisionProposal.from_json(raw_json)

    assert proposal == restored
    assert restored.epistemic_status == EpistemicStatus.INFERENCE
    assert restored.proposal_status == ProposalStatus.PROPOSAL


def test_reject_missing_evidence() -> None:
    """Rule 3: NO EVIDENCE -> NO CLAIM. Empty evidence list must fail."""
    payload = _build_valid_proposal()
    payload["required_evidence"] = []

    with pytest.raises(ValidationError) as exc_info:
        DecisionProposal(**payload)

    assert "required_evidence" in str(exc_info.value)


def test_reject_invalid_epistemic_status() -> None:
    """Rule 2: Anti-Hallucination. Invalid epistemic states must be rejected."""
    payload = _build_valid_proposal()
    payload["epistemic_status"] = "GUESS"  # type: ignore[dict-item]

    with pytest.raises(ValidationError):
        DecisionProposal(**payload)


def test_reject_invalid_agent_family() -> None:
    """Rule 1 & 8: Only defined agent families can produce proposals."""
    payload = _build_valid_proposal()
    payload["agent_family"] = "EXECUTION"  # type: ignore[dict-item]

    with pytest.raises(ValidationError) as exc_info:
        DecisionProposal(**payload)

    assert "agent_family" in str(exc_info.value)


def test_confidence_vector_bounds_enforced() -> None:
    """Rule 7: Confidence vector dimensions must be strictly between 0.0 and 1.0."""
    payload = _build_valid_proposal()
    payload["confidence_vector"]["evidence_quality"] = 1.5  # type: ignore[index]

    with pytest.raises(ValidationError):
        DecisionProposal(**payload)


def test_contradiction_final_stance_enum() -> None:
    """Rule 11: Contradiction stance must be one of the allowed states including NO_DECISION."""
    payload = _build_valid_proposal()
    payload["contradiction_report"]["final_stance"] = "MAYBE"  # type: ignore[index]

    with pytest.raises(ValidationError):
        DecisionProposal(**payload)

    # Verify NO_DECISION is explicitly allowed
    payload["contradiction_report"]["final_stance"] = "NO_DECISION"  # type: ignore[index]
    proposal = DecisionProposal(**payload)
    assert proposal.contradiction_report.final_stance == "NO_DECISION"


def test_immutability_enforced() -> None:
    """Rule 10 & Governance: Contracts must be frozen after creation."""
    payload = _build_valid_proposal()
    proposal = DecisionProposal(**payload)

    with pytest.raises(ValidationError):
        proposal.epistemic_status = EpistemicStatus.FACT  # type: ignore[misc]
