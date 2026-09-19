"""
Integration Bridge: Legacy Agent Output to Unified Decision Proposal.
Translates ResearchDecision into the governance-enforced DecisionProposal
schema without mutating original agents.
Contains ZERO business logic or trading decisions.
"""
from __future__ import annotations

from intelligence.contracts.unified_decision_proposal import (
    AdversarialValidation,
    ConfidenceVector,
    ContradictionReport,
    DecisionProposal,
    EpistemicStatus,
    EvidenceRecord,
    MemoryProvenance,
    ProposalStatus,
)
from intelligence.research_agent.models import ResearchDecision

_ACTION_TO_STATUS: dict[str, ProposalStatus] = {
    "investigate": ProposalStatus.HYPOTHESIS,
    "alert": ProposalStatus.ESCALATED,
    "ignore": ProposalStatus.REJECTED,
    "archive": ProposalStatus.OBSERVED,
}

_ACTION_TO_EPISTEMIC: dict[str, EpistemicStatus] = {
    "investigate": EpistemicStatus.INFERENCE,
    "alert": EpistemicStatus.FACT,
    "ignore": EpistemicStatus.UNKNOWN,
    "archive": EpistemicStatus.HYPOTHESIS,
}


def translate_research_decision(
    decision: ResearchDecision,
) -> DecisionProposal:
    """
    Translate a frozen ResearchDecision into a frozen DecisionProposal.

    Args:
        decision: The validated Pydantic V2 ResearchDecision from agent.

    Returns:
        A fully validated, frozen DecisionProposal ready for Chaos Engine.
    """
    confidence_vector = ConfidenceVector(
        evidence_quality=decision.confidence,
        source_reliability=decision.confidence,
        data_freshness=decision.confidence,
        cross_validation=0.5,
        historical_accuracy=0.5,
        regime_compatibility=0.5,
        contradiction_level=0.0,
        adversarial_survival=1.0,
        risk_compatibility=0.5,
    )

    evidence_record = EvidenceRecord(
        evidence_id=f"ev-{decision.trace_id}",
        source=decision.agent_id,
        source_type="legacy_reasoning",
        timestamp_ns=decision.timestamp_ms * 1_000_000,
        quality_score=decision.confidence,
        reliability_score=decision.confidence,
        cross_check_status="PENDING_BRIDGE_VALIDATION",
    )

    memory_provenance_list: list[MemoryProvenance] = [
        MemoryProvenance(
            memory_id=ref,
            memory_type="episodic",
            retrieved_context="legacy_reference",
            regime_at_creation="UNKNOWN_REGIME",
            failure_count=0,
            status="VALIDATED",
        )
        for ref in decision.memory_refs
    ]

    proposal_status = _ACTION_TO_STATUS.get(
        decision.action, ProposalStatus.PROPOSAL
    )
    epistemic_status = _ACTION_TO_EPISTEMIC.get(
        decision.action, EpistemicStatus.UNKNOWN
    )

    default_adversarial = AdversarialValidation(
        tested_by_agent="pending_chaos_engine",
        overfitting_detected=False,
        regime_failure_risk=0.5,
        data_leakage_risk=0.5,
        survival_score=0.5,
    )

    default_contradiction = ContradictionReport(
        contradiction_detected=False,
        conflicting_agents=[],
        resolution_method="pending_evaluation",
        final_stance="NEUTRAL",
    )

    return DecisionProposal(
        proposal_id=f"prop-{decision.trace_id}",
        producer_agent_id=decision.agent_id,
        agent_family="INTELLIGENCE",
        timestamp_ns=decision.timestamp_ms * 1_000_000,
        epistemic_status=epistemic_status,
        proposal_status=proposal_status,
        target_strategy=f"legacy_{decision.action}_{decision.symbol}",
        proposed_action=decision.action.upper(),
        payload={"original_reasoning": decision.reasoning},
        required_evidence=[evidence_record],
        memory_provenance=memory_provenance_list,
        confidence_vector=confidence_vector,
        independent_validator_id=None,
        adversarial_report=default_adversarial,
        known_failures_from_memory=[],
        contradiction_report=default_contradiction,
        requires_human_approval=(decision.action == "alert"),
        audit_log_ref=f"audit-{decision.trace_id}",
    )
