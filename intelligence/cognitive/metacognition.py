"""
Metacognition Engine — System awareness of its own reasoning process.
Evaluates confidence, uncertainty, and justification before action.

Governed by:
- CG-1: No Action Without Reflection
- CG-3: Audit Every Thought (not just actions)
- Principle 3: "I notice my mind is generating a decision" vs "I decide"
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class ConfidenceLevel(StrEnum):
    """Metacognitive confidence assessment levels."""
    HIGH = "high"           # Strong evidence, low uncertainty
    MODERATE = "moderate"   # Some evidence, manageable uncertainty
    LOW = "low"             # Weak evidence, high uncertainty
    CRITICAL = "critical"   # Contradictory evidence, halt recommended


@dataclass(frozen=True)
class MetacognitiveAssessment:
    """
    Immutable record of system's self-awareness about a decision.
    Frozen to prevent post-assessment mutation (Governance Rule 10).
    """
    confidence: ConfidenceLevel
    epistemic_score: float      # 0.0 = total ignorance, 1.0 = full knowledge
    uncertainty_sources: tuple[str, ...]
    justification: str          # WHY the system believes what it believes
    veto_recommended: bool      # Should Algebraic Veto override?


class MetacognitionEngine:
    """
    Evaluates the quality of the system's own reasoning.
    Does NOT make trading decisions. Only assesses decision readiness.
    """

    # Thresholds governed by risk policy
    EPISTEMIC_HIGH_THRESHOLD = 0.8
    EPISTEMIC_LOW_THRESHOLD = 0.4
    SURVIVAL_CRITICAL_THRESHOLD = 0.3

    @classmethod
    def assess(
        cls,
        survival_score: float,
        world_model_probs: list[float] | None,
        evidence_count: int,
        signal_confidence: float,
    ) -> MetacognitiveAssessment:
        """
        Perform metacognitive evaluation of current decision state.

        Implements Principle 3: The system observes its own thinking
        process rather than blindly executing it.

        Args:
            survival_score: From ChaosEngine adversarial testing.
            world_model_probs: From Rust Markov chain prediction.
            evidence_count: Number of supporting evidence references.
            signal_confidence: Raw confidence from ResearchAgent.

        Returns:
            Frozen MetacognitiveAssessment with justification.
        """
        uncertainties: list[str] = []
        epistemic_score = 0.0

        # Factor 1: Evidence depth
        if evidence_count == 0:
            uncertainties.append("no_evidence_refs")
        elif evidence_count < 3:
            uncertainties.append("insufficient_evidence")
            epistemic_score += 0.2
        else:
            epistemic_score += 0.4

        # Factor 2: Survival score (adversarial resilience)
        if survival_score < cls.SURVIVAL_CRITICAL_THRESHOLD:
            uncertainties.append("low_survival_score")
        else:
            epistemic_score += 0.3 * survival_score

        # Factor 3: World model alignment
        if world_model_probs is None:
            uncertainties.append("world_model_unavailable")
        else:
            max_prob = max(world_model_probs) if world_model_probs else 0.0
            if max_prob < 0.5:
                uncertainties.append("ambiguous_regime_prediction")
                epistemic_score += 0.1
            else:
                epistemic_score += 0.3 * max_prob

        # Factor 4: Signal confidence
        epistemic_score += 0.2 * signal_confidence

        # Clamp to [0.0, 1.0]
        epistemic_score = max(0.0, min(1.0, epistemic_score))

        # Determine confidence level
        if epistemic_score >= cls.EPISTEMIC_HIGH_THRESHOLD and not uncertainties:
            confidence = ConfidenceLevel.HIGH
            veto = False
        elif epistemic_score >= cls.EPISTEMIC_LOW_THRESHOLD:
            confidence = ConfidenceLevel.MODERATE
            veto = False
        elif epistemic_score >= cls.SURVIVAL_CRITICAL_THRESHOLD:
            confidence = ConfidenceLevel.LOW
            veto = False
        else:
            confidence = ConfidenceLevel.CRITICAL
            veto = True

        # Build justification string (CG-3: Audit Every Thought)
        justification = (
            f"epistemic={epistemic_score:.2f}, "
            f"survival={survival_score:.2f}, "
            f"evidence={evidence_count}, "
            f"uncertainties={len(uncertainties)}"
        )

        assessment = MetacognitiveAssessment(
            confidence=confidence,
            epistemic_score=epistemic_score,
            uncertainty_sources=tuple(uncertainties),
            justification=justification,
            veto_recommended=veto,
        )

        logger.info(
            "METACOGNITION_ASSESSMENT",
            extra={
                "confidence": confidence.value,
                "epistemic_score": round(epistemic_score, 3),
                "veto": veto,
                "justification": justification,
            },
        )

        return assessment
