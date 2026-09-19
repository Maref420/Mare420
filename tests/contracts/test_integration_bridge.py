"""
Validation tests for Legacy to Unified Integration Bridge.
Ensures ResearchAgent outputs can safely enter the new governance pipeline.
"""
from __future__ import annotations

from typing import Any

import pytest

from intelligence.contracts.unified_decision_proposal import (
    DecisionProposal,
    EpistemicStatus,
    ProposalStatus,
)
from intelligence.integration_bridge.legacy_to_unified import (
    translate_research_decision,
)
from intelligence.research_agent.models import ResearchDecision


def _build_legacy_decision(**overrides: Any) -> ResearchDecision:
    """Simulate exact output of ResearchAgent.process_signal()."""
    base: dict[str, Any] = {
        "symbol": "BTCUSDT",
        "action": "investigate",
        "confidence": 0.87,
        "reasoning": "AQS=85, toxicity=0.1, spoofing=False",
        "memory_refs": ["pattern_01", "pattern_02"],
        "trace_id": "trace-bridge-001",
        "timestamp_ms": 1726800000000,
    }
    base.update(overrides)
    return ResearchDecision(**base)


def test_translate_investigate_action_maps_correctly() -> None:
    """Ensure investigate maps to HYPOTHESIS and INFERENCE."""
    legacy = _build_legacy_decision()
    proposal = translate_research_decision(legacy)

    assert proposal.proposal_status == ProposalStatus.HYPOTHESIS
    assert proposal.epistemic_status == EpistemicStatus.INFERENCE
    assert proposal.target_strategy == "legacy_investigate_BTCUSDT"
    assert proposal.proposed_action == "INVESTIGATE"
    assert proposal.producer_agent_id == "research_agent"


def test_translate_alert_requires_human_approval() -> None:
    """Rule: Alert actions must trigger human approval gate."""
    legacy = _build_legacy_decision(action="alert", confidence=0.95)
    proposal = translate_research_decision(legacy)

    assert proposal.proposal_status == ProposalStatus.ESCALATED
    assert proposal.epistemic_status == EpistemicStatus.FACT
    assert proposal.requires_human_approval is True


def test_translate_preserves_evidence_and_memory() -> None:
    """Ensure legacy reasoning becomes Evidence and refs become Provenance."""
    legacy = _build_legacy_decision()
    proposal = translate_research_decision(legacy)

    assert len(proposal.required_evidence) == 1
    assert proposal.required_evidence[0].source == "research_agent"
    assert proposal.required_evidence[0].quality_score == 0.87
    assert len(proposal.memory_provenance) == 2
    assert proposal.memory_provenance[0].memory_id == "pattern_01"


def test_translate_confidence_is_exact() -> None:
    """Since ResearchDecision enforces [0.0, 1.0], bridge needs no clamping."""
    legacy = _build_legacy_decision(confidence=0.42)
    proposal = translate_research_decision(legacy)

    assert proposal.confidence_vector.evidence_quality == 0.42
    assert proposal.confidence_vector.source_reliability == 0.42


def test_translate_rejects_invalid_action() -> None:
    """Ensure Pydantic rejects invalid actions before bridge sees them."""
    with pytest.raises(Exception):
        _build_legacy_decision(action="execute_trade")


def test_translated_proposal_survives_full_pipeline() -> None:
    """
    INTEGRATION TEST: Prove that a translated legacy decision can pass
    through Chaos Engine and Policy Evaluator without crashing.
    """
    from intelligence.adversarial_lab.chaos_engine import ChaosEngine
    from intelligence.agent_control_plane.policy.decision_evaluator import (
        evaluate_proposal,
    )

    legacy = _build_legacy_decision()
    proposal = translate_research_decision(legacy)

    chaos = ChaosEngine(seed=42)
    adv_report = chaos.stress_test(proposal)

    prop_dict = proposal.model_dump()
    prop_dict["adversarial_report"] = adv_report.model_dump()
    stressed_proposal = DecisionProposal(**prop_dict)

    decision, reason = evaluate_proposal(stressed_proposal)

    assert decision in ("ALLOW", "DENY", "HOLD", "QUARANTINE")
    assert reason is not None
