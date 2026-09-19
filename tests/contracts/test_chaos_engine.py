"""
Validation tests for Automated Chaos Injection Engine.
Ensures adversarial validation correctly identifies fragile proposals.
"""
from __future__ import annotations

from datetime import UTC, datetime

from intelligence.adversarial_lab.chaos_engine import ChaosEngine
from intelligence.contracts.unified_decision_proposal import (
    AdversarialValidation,
    ConfidenceVector,
    ContradictionReport,
    DecisionProposal,
    EpistemicStatus,
    EvidenceRecord,
    ProposalStatus,
)


def _build_proposal(
    evidence_count: int = 2,
    regime_compatibility: float = 0.9,
) -> DecisionProposal:
    """Helper to build proposals with configurable resilience."""
    ts = int(datetime.now(UTC).timestamp() * 1e9)
    evidence_list = [
        EvidenceRecord(
            evidence_id=f"ev-{i}",
            source="test_source",
            source_type="test",
            timestamp_ns=ts,
            quality_score=0.9,
            reliability_score=0.9,
            cross_check_status="VERIFIED",
        )
        for i in range(evidence_count)
    ]

    return DecisionProposal(
        proposal_id="prop-chaos-001",
        producer_agent_id="test-agent",
        agent_family="INTELLIGENCE",
        timestamp_ns=ts,
        epistemic_status=EpistemicStatus.INFERENCE,
        proposal_status=ProposalStatus.PROPOSAL,
        target_strategy="test_strategy",
        proposed_action="BUY_SIGNAL",
        payload={},
        required_evidence=evidence_list,
        memory_provenance=[],
        confidence_vector=ConfidenceVector(
            evidence_quality=0.9,
            source_reliability=0.9,
            data_freshness=0.9,
            cross_validation=0.8,
            historical_accuracy=0.85,
            regime_compatibility=regime_compatibility,
            contradiction_level=0.1,
            adversarial_survival=0.8,
            risk_compatibility=0.85,
        ),
        independent_validator_id="validator-01",
        adversarial_report=AdversarialValidation(
            tested_by_agent="pre-test",
            overfitting_detected=False,
            regime_failure_risk=0.1,
            data_leakage_risk=0.1,
            survival_score=0.9,
        ),
        known_failures_from_memory=[],
        contradiction_report=ContradictionReport(
            contradiction_detected=False,
            conflicting_agents=[],
            resolution_method="none",
            final_stance="BULLISH",
        ),
        requires_human_approval=False,
        audit_log_ref="audit-001",
    )


def test_chaos_engine_returns_adversarial_validation() -> None:
    """Ensure output matches the AdversarialValidation schema exactly."""
    engine = ChaosEngine(seed=42)
    proposal = _build_proposal()

    result = engine.stress_test(proposal)

    assert isinstance(result, AdversarialValidation)
    assert result.tested_by_agent == "chaos-engine-v1"
    assert 0.0 <= result.survival_score <= 1.0
    assert 0.0 <= result.regime_failure_risk <= 1.0
    assert 0.0 <= result.data_leakage_risk <= 1.0


def test_single_evidence_detected_as_fragile() -> None:
    """Rule 3: Proposals with single evidence must have high leakage risk."""
    engine = ChaosEngine(seed=42)
    fragile_proposal = _build_proposal(evidence_count=1)

    result = engine.stress_test(fragile_proposal)

    # Single evidence means evidence removal survival is 0.0
    assert result.data_leakage_risk == 1.0  # 1.0 - 0.0


def test_multiple_evidence_detected_as_resilient() -> None:
    """Proposals with redundant evidence should have lower leakage risk."""
    engine = ChaosEngine(seed=42)
    resilient_proposal = _build_proposal(evidence_count=3)

    result = engine.stress_test(resilient_proposal)

    assert result.data_leakage_risk == 0.0  # 1.0 - 1.0


def test_low_regime_compatibility_increases_failure_risk() -> None:
    """Rule 11: Low regime compatibility must increase regime failure risk."""
    engine = ChaosEngine(seed=42)
    low_regime_proposal = _build_proposal(regime_compatibility=0.2)

    result = engine.stress_test(low_regime_proposal)

    assert result.regime_failure_risk == 0.8  # 1.0 - 0.2


def test_deterministic_with_seed() -> None:
    """Ensure same seed produces identical stress test results."""
    proposal = _build_proposal()

    engine_1 = ChaosEngine(seed=123)
    result_1 = engine_1.stress_test(proposal)

    engine_2 = ChaosEngine(seed=123)
    result_2 = engine_2.stress_test(proposal)

    assert result_1.survival_score == result_2.survival_score
    assert result_1.overfitting_detected == result_2.overfitting_detected


def test_immutability_of_original_proposal() -> None:
    """Rule 10: Chaos Engine must NOT mutate the frozen proposal."""
    engine = ChaosEngine(seed=42)
    proposal = _build_proposal()
    original_score = proposal.confidence_vector.evidence_quality

    engine.stress_test(proposal)

    assert proposal.confidence_vector.evidence_quality == original_score
