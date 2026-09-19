"""
Validation tests for Decision Proposal Envelope Adapter.
Ensures Python output matches Go Message Broker expected format.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from intelligence.contracts.envelope_adapter import wrap_decision_proposal
from intelligence.contracts.unified_decision_proposal import (
    AdversarialValidation,
    ConfidenceVector,
    ContradictionReport,
    DecisionProposal,
    EpistemicStatus,
    EvidenceRecord,
    ProposalStatus,
)


def _build_valid_proposal() -> DecisionProposal:
    """Helper to build a canonical valid proposal."""
    return DecisionProposal(
        proposal_id="prop-001",
        producer_agent_id="market-agent-01",
        agent_family="INTELLIGENCE",
        timestamp_ns=int(datetime.now(UTC).timestamp() * 1e9),
        epistemic_status=EpistemicStatus.INFERENCE,
        proposal_status=ProposalStatus.PROPOSAL,
        target_strategy="momentum_btc_v1",
        proposed_action="BUY_SIGNAL",
        payload={},
        required_evidence=[
            EvidenceRecord(
                evidence_id="ev-001",
                source="orderbook_feed",
                source_type="market_data",
                timestamp_ns=int(datetime.now(UTC).timestamp() * 1e9),
                quality_score=0.9,
                reliability_score=0.95,
                cross_check_status="VERIFIED",
            )
        ],
        memory_provenance=[],
        confidence_vector=ConfidenceVector(
            evidence_quality=0.9,
            source_reliability=0.9,
            data_freshness=0.9,
            cross_validation=0.8,
            historical_accuracy=0.85,
            regime_compatibility=0.9,
            contradiction_level=0.1,
            adversarial_survival=0.8,
            risk_compatibility=0.85,
        ),
        independent_validator_id="validator-01",
        adversarial_report=AdversarialValidation(
            tested_by_agent="adversarial-01",
            overfitting_detected=False,
            regime_failure_risk=0.2,
            data_leakage_risk=0.05,
            survival_score=0.85,
        ),
        known_failures_from_memory=[],
        contradiction_report=ContradictionReport(
            contradiction_detected=False,
            conflicting_agents=[],
            resolution_method="none_required",
            final_stance="BULLISH",
        ),
        requires_human_approval=True,
        audit_log_ref="audit-ref-001",
    )


def test_envelope_structure_matches_go_expectations() -> None:
    """Ensure wrapped envelope has all fields required by validator.go."""
    proposal = _build_valid_proposal()
    raw_bytes = wrap_decision_proposal(proposal)
    envelope: dict[str, Any] = json.loads(raw_bytes.decode("utf-8"))

    assert envelope["contract_version"] == "1.0"
    assert envelope["message_type"] == "decision-proposal-v1"
    assert envelope["source_engine"] == "python_ai"
    assert "timestamp" in envelope
    assert isinstance(envelope["payload"], dict)
    assert envelope["payload"]["proposal_id"] == "prop-001"


def test_envelope_payload_is_valid_json() -> None:
    """Ensure payload is correctly serialized without data loss."""
    proposal = _build_valid_proposal()
    raw_bytes = wrap_decision_proposal(proposal)
    envelope: dict[str, Any] = json.loads(raw_bytes.decode("utf-8"))

    assert envelope["payload"]["epistemic_status"] == "INFERENCE"
    assert envelope["payload"]["confidence_vector"]["evidence_quality"] == 0.9
    assert len(envelope["payload"]["required_evidence"]) == 1


def test_envelope_metadata_contains_governance_flags() -> None:
    """Ensure metadata carries governance context."""
    proposal = _build_valid_proposal()
    raw_bytes = wrap_decision_proposal(proposal)
    envelope: dict[str, Any] = json.loads(raw_bytes.decode("utf-8"))

    assert envelope["metadata"]["specification_id"] == "unified-decision-proposal-v1"
    assert envelope["metadata"]["validation_status"] == "pending_control_plane"
