"""
Deterministic Decision Policy Evaluator for Atlas AI Control Plane.
Evaluates Unified Decision Proposals against Anti-Hallucination Matrix rules.
Contains ZERO business logic or trading decisions.
Outputs strictly: ALLOW, DENY, HOLD, QUARANTINE.
"""
from __future__ import annotations

from enum import StrEnum

from intelligence.contracts.unified_decision_proposal import (
    DecisionProposal,
    EpistemicStatus,
)


class PolicyDecision(StrEnum):
    """Strict authorization outcomes governed by Control Plane."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    HOLD = "HOLD"
    QUARANTINE = "QUARANTINE"


class PolicyReason(StrEnum):
    """Deterministic reasons for policy decisions."""

    PASSED_ALL_CHECKS = "PASSED_ALL_CHECKS"
    NO_EVIDENCE = "NO_EVIDENCE"
    UNKNOWN_EPISTEMIC_ACTION = "UNKNOWN_EPISTEMIC_ACTION"
    CONTRADICTION_NO_DECISION = "CONTRADICTION_NO_DECISION"
    ADVERSARIAL_SURVIVAL_LOW = "ADVERSARIAL_SURVIVAL_LOW"
    REQUIRES_HUMAN_APPROVAL = "REQUIRES_HUMAN_APPROVAL"
    RISK_COMPATIBILITY_LOW = "RISK_COMPATIBILITY_LOW"


# Configurable thresholds (Governance controlled)
MIN_ADVERSARIAL_SURVIVAL = 0.5
MIN_RISK_COMPATIBILITY = 0.5


def evaluate_proposal(proposal: DecisionProposal) -> tuple[PolicyDecision, PolicyReason]:
    """
    Evaluate a frozen DecisionProposal against Atlas Governance Rules.
    
    Args:
        proposal: The immutable DecisionProposal to evaluate.
        
    Returns:
        Tuple of (PolicyDecision, PolicyReason).
    """
    # Rule: NO EVIDENCE -> NO CLAIM -> DENY
    if not proposal.required_evidence:
        return PolicyDecision.DENY, PolicyReason.NO_EVIDENCE

    # Rule: ANTI-HALLUCINATION -> UNKNOWN cannot trigger action
    if proposal.epistemic_status == EpistemicStatus.UNKNOWN:
        if proposal.proposed_action not in ("HOLD", "NO_ACTION"):
            return PolicyDecision.QUARANTINE, PolicyReason.UNKNOWN_EPISTEMIC_ACTION

    # Rule: CONTRADICTION -> NO AUTOMATIC EXECUTION -> HOLD
    if proposal.contradiction_report.final_stance == "NO_DECISION":
        return PolicyDecision.HOLD, PolicyReason.CONTRADICTION_NO_DECISION

    # Rule: ADVERSARIAL VALIDATION mandatory
    if proposal.adversarial_report.survival_score < MIN_ADVERSARIAL_SURVIVAL:
        return PolicyDecision.DENY, PolicyReason.ADVERSARIAL_SURVIVAL_LOW

    # Rule: RISK COMPATIBILITY mandatory
    if proposal.confidence_vector.risk_compatibility < MIN_RISK_COMPATIBILITY:
        return PolicyDecision.DENY, PolicyReason.RISK_COMPATIBILITY_LOW

    # Rule: HUMAN APPROVAL required before execution
    if proposal.requires_human_approval:
        return PolicyDecision.HOLD, PolicyReason.REQUIRES_HUMAN_APPROVAL

    # All checks passed
    return PolicyDecision.ALLOW, PolicyReason.PASSED_ALL_CHECKS
