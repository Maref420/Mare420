"""
Automated Chaos Injection Engine for Atlas AI Adversarial Lab.
Stresses DecisionProposals before they reach the Control Plane.
Contains ZERO business logic or trading decisions.
"""
from __future__ import annotations

import random

from intelligence.contracts.unified_decision_proposal import (
    AdversarialValidation,
    DecisionProposal,
)


class ChaosEngine:
    """
    Injects structured chaos into DecisionProposals to detect
    overfitting, fragility, and hallucination risks.
    """

    def __init__(self, seed: int | None = None) -> None:
        """Initialize with optional deterministic seed for reproducibility."""
        self._rng = random.Random(seed)

    def stress_test(self, proposal: DecisionProposal) -> AdversarialValidation:
        """
        Run all chaos scenarios against a frozen DecisionProposal.

        Args:
            proposal: The immutable DecisionProposal to stress test.

        Returns:
            AdversarialValidation report containing survival metrics.
        """
        noise_survival = self._inject_noise(proposal)
        evidence_survival = self._remove_evidence(proposal)
        regime_survival = self._simulate_regime_shift(proposal)

        # Calculate composite survival score (weighted average)
        survival_score = (
            (noise_survival * 0.4)
            + (evidence_survival * 0.3)
            + (regime_survival * 0.3)
        )

        # Detect overfitting if confidence drops drastically under noise
        overfitting_detected = noise_survival < 0.5

        return AdversarialValidation(
            tested_by_agent="chaos-engine-v1",
            overfitting_detected=overfitting_detected,
            regime_failure_risk=1.0 - regime_survival,
            data_leakage_risk=1.0 - evidence_survival,
            survival_score=survival_score,
        )

    def _inject_noise(self, proposal: DecisionProposal) -> float:
        """
        Perturb confidence vector dimensions by +/- 10%.
        Returns survival ratio (how many dimensions remained above threshold).
        """
        cv_dict = proposal.confidence_vector.model_dump()
        original_values: list[float] = [
            v for v in cv_dict.values() if isinstance(v, float)
        ]

        if not original_values:
            return 1.0

        survived = 0
        threshold = 0.5  # Minimum acceptable confidence dimension

        for val in original_values:
            perturbation = self._rng.uniform(-0.1, 0.1)
            perturbed_val = max(0.0, min(1.0, val + perturbation))
            if perturbed_val >= threshold:
                survived += 1

        return survived / len(original_values)

    def _remove_evidence(self, proposal: DecisionProposal) -> float:
        """
        Simulate loss of one evidence record.
        Returns 1.0 if multiple evidences exist (resilient), 0.0 if only one.
        """
        evidence_count = len(proposal.required_evidence)
        if evidence_count <= 1:
            return 0.0  # Fragile: single point of failure
        return 1.0  # Resilient: redundant evidence exists

    def _simulate_regime_shift(self, proposal: DecisionProposal) -> float:
        """
        Evaluate regime compatibility score from confidence vector.
        If the proposal already has low regime compatibility, risk is high.
        """
        regime_compat = proposal.confidence_vector.regime_compatibility
        # Survival is directly proportional to regime compatibility
        return float(regime_compat)
