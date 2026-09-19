"""
Validation tests for Deterministic Decision Policy Evaluator.
Ensures Control Plane rules are strictly enforced without exceptions.
"""
from __future__ import annotations

from datetime import UTC, datetime

from intelligence.agent_control_plane.policy.decision_evaluator import (
    PolicyDecision,
    PolicyReason,
    evaluate_proposal,
)
from intelligence.contracts.unified_decision_proposal import (
    DecisionProposal,
    EpistemicStatus,
    ProposalStatus,
)


def _build_base_proposal(**overrides: object) -> DecisionProposal:
    """Helper to build a canonical valid proposal with optional overrides."""
    ts = int(datetime.now(UTC).timestamp() * 1e9)
    base: dict[str, object] = {
        "proposal_id": "prop-pol-001",
        "producer_agent_id": "test-agent",
        "agent_family": "INTELLIGENCE",
        "timestamp_ns": ts,
        "epistemic_status": EpistemicStatus.INFERENCE.value,
        "proposal_status": ProposalStatus.PROPOSAL.value,
        "target_strategy": "test_strategy",
        "proposed_action": "BUY_SIGNAL",
        "payload": {},
        "required_evidence": [
            {
                "evidence_id": "ev-001",
                "source": "test",
                "source_type": "test",
                "timestamp_ns": ts,
                "quality_score": 0.9,
                "reliability_score": 0.9,
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
            "tested_by_agent": "chaos-engine-v1",
            "overfitting_detected": False,
            "regime_failure_risk": 0.2,
            "data_leakage_risk": 0.1,
            "survival_score": 0.85,
        },
        "known_failures_from_memory": [],
        "contradiction_report": {
            "contradiction_detected": False,
            "conflicting_agents": [],
            "resolution_method": "none",
            "final_stance": "BULLISH",
        },
        "requires_human_approval": False,
        "audit_log_ref": "audit-001",
    }
    base.update(overrides)

    # Use model_construct to bypass validation for Policy Engine testing
    # This allows testing governance rules on structurally invalid data
    if overrides.get("required_evidence") == []:
        return DecisionProposal.model_construct(**base)  # type: ignore[arg-type]

    return DecisionProposal(**base)  # type: ignore[arg-type]


def test_valid_proposal_is_allowed() -> None:
    """Ensure a fully compliant proposal receives ALLOW."""
    proposal = _build_base_proposal()
    decision, reason = evaluate_proposal(proposal)

    assert decision == PolicyDecision.ALLOW
    assert reason == PolicyReason.PASSED_ALL_CHECKS


def test_no_evidence_is_denied() -> None:
    """Rule: NO EVIDENCE -> NO CLAIM -> DENY."""
    proposal = _build_base_proposal(required_evidence=[])
    decision, reason = evaluate_proposal(proposal)

    assert decision == PolicyDecision.DENY
    assert reason == PolicyReason.NO_EVIDENCE


def test_unknown_epistemic_with_action_is_quarantined() -> None:
    """Rule: UNKNOWN epistemic status attempting action -> QUARANTINE."""
    proposal = _build_base_proposal(
        epistemic_status=EpistemicStatus.UNKNOWN.value,
        proposed_action="BUY_SIGNAL",
    )
    decision, reason = evaluate_proposal(proposal)

    assert decision == PolicyDecision.QUARANTINE
    assert reason == PolicyReason.UNKNOWN_EPISTEMIC_ACTION


def test_unknown_epistemic_with_hold_is_allowed() -> None:
    """Exception: UNKNOWN epistemic status requesting HOLD is safe."""
    proposal = _build_base_proposal(
        epistemic_status=EpistemicStatus.UNKNOWN.value,
        proposed_action="HOLD",
    )
    decision, reason = evaluate_proposal(proposal)

    assert decision == PolicyDecision.ALLOW
    assert reason == PolicyReason.PASSED_ALL_CHECKS


def test_contradiction_no_decision_is_held() -> None:
    """Rule: CONTRADICTION -> NO AUTOMATIC EXECUTION -> HOLD."""
    proposal = _build_base_proposal(
        contradiction_report={
            "contradiction_detected": True,
            "conflicting_agents": ["agent-a", "agent-b"],
            "resolution_method": "none",
            "final_stance": "NO_DECISION",
        }
    )
    decision, reason = evaluate_proposal(proposal)

    assert decision == PolicyDecision.HOLD
    assert reason == PolicyReason.CONTRADICTION_NO_DECISION


def test_low_adversarial_survival_is_denied() -> None:
    """Rule: Adversarial survival below threshold -> DENY."""
    proposal = _build_base_proposal(
        adversarial_report={
            "tested_by_agent": "chaos-engine-v1",
            "overfitting_detected": True,
            "regime_failure_risk": 0.8,
            "data_leakage_risk": 0.7,
            "survival_score": 0.3,
        }
    )
    decision, reason = evaluate_proposal(proposal)

    assert decision == PolicyDecision.DENY
    assert reason == PolicyReason.ADVERSARIAL_SURVIVAL_LOW


def test_requires_human_approval_is_held() -> None:
    """Rule: Human approval required -> HOLD until granted."""
    proposal = _build_base_proposal(requires_human_approval=True)
    decision, reason = evaluate_proposal(proposal)

    assert decision == PolicyDecision.HOLD
    assert reason == PolicyReason.REQUIRES_HUMAN_APPROVAL


def test_low_risk_compatibility_is_denied() -> None:
    """Rule: Risk compatibility below threshold -> DENY."""
    proposal = _build_base_proposal(
        confidence_vector={
            "evidence_quality": 0.9,
            "source_reliability": 0.9,
            "data_freshness": 0.9,
            "cross_validation": 0.8,
            "historical_accuracy": 0.85,
            "regime_compatibility": 0.9,
            "contradiction_level": 0.1,
            "adversarial_survival": 0.8,
            "risk_compatibility": 0.2,
        }
    )
    decision, reason = evaluate_proposal(proposal)

    assert decision == PolicyDecision.DENY
    assert reason == PolicyReason.RISK_COMPATIBILITY_LOW
