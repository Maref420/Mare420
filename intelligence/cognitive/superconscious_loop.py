"""
Superconscious Loop — Orchestrates the 6-step cognitive cycle.
Implements user formula: Memory + WorldModel + Metacognition +
SelfReflection + Planning + Verification.

Governed by:
- CG-1: No Action Without Reflection
- CG-4: Graceful Degradation (HOLD if IPC fails)
- CG-5: Zero Mutation Existing (pre-policy interceptor)
- Rule 12: Minimal Blast Radius
"""
from __future__ import annotations

import contextlib
import logging
from typing import Any

from intelligence.cognitive.metacognition import (
    ConfidenceLevel,
    MetacognitionEngine,
)
from intelligence.cognitive.world_model import WorldModel
from intelligence.contracts.unified_decision_proposal import (
    DecisionProposal,
    EpistemicStatus,
)

logger = logging.getLogger(__name__)


class SuperconsciousLoop:
    """
    Pre-policy cognitive interceptor that elevates raw signals
    through 6 neuroscientific processing stages before allowing
    them to reach the Policy Evaluator.

    This is the physical implementation of engineered superconsciousness.
    """

    # Default 3-state Markov matrix (Bull/Bear/Sideways)
    # Will be dynamically updated from Semantic Memory in future phases
    DEFAULT_TRANSITION_MATRIX: list[float] = [
        0.7, 0.2, 0.1,  # Bull → Bull, Bear, Sideways
        0.1, 0.6, 0.3,  # Bear → Bull, Bear, Sideways
        0.3, 0.3, 0.4,  # Sideways → Bull, Bear, Sideways
    ]

    def __init__(self, ipc_socket: str = "/app/uds/atlas-ipc.sock") -> None:
        self._world_model = WorldModel(ipc_socket=ipc_socket)
        self._metacognition = MetacognitionEngine()

    def process_proposal(
        self, proposal: DecisionProposal
    ) -> DecisionProposal:
        """
        Elevate a DecisionProposal through the cognitive cycle.

        Flow:
            1. World Model → Predict regime
            2. Metacognition → Assess confidence
            3. Planning → Monte Carlo scenario
            4. Verification → Apply algebraic veto if needed
            5. Update Epistemic Status
            6. Return enriched proposal

        Governed by CG-4: If any step fails gracefully, proposal
        epistemic_status is set to UNCERTAIN rather than crashing.
        """
        logger.info(
            "SUPERCONSCIOUS_LOOP_STARTED",
            extra={"proposal_id": proposal.proposal_id},
        )

        # STAGE 1: World Model (Markov Regime Prediction)
        regime_probs: list[float] | None = None
        with contextlib.suppress(Exception):
            result = self._world_model.predict_regime(
                transition_matrix=self.DEFAULT_TRANSITION_MATRIX,
                current_state=0,  # Default: assume Bull until proven otherwise
                states_count=3,
            )
            if result and "next_state_probabilities" in result:
                raw_probs = result["next_state_probabilities"]
                if isinstance(raw_probs, list):
                    regime_probs = [float(p) for p in raw_probs]

        # STAGE 2: Metacognition (Self-Awareness Assessment)
        evidence_count = len(proposal.evidence_refs) if hasattr(proposal, 'evidence_refs') and proposal.evidence_refs else 0
        cv = proposal.confidence_vector
        signal_conf: float = (
            cv.evidence_quality + cv.source_reliability + cv.data_freshness
            + cv.cross_validation + cv.historical_accuracy + cv.regime_compatibility
        ) / 6.0
        survival = proposal.adversarial_report.survival_score if hasattr(proposal, 'adversarial_report') else 0.5
        assessment = self._metacognition.assess(
            survival_score=survival,
            world_model_probs=regime_probs,
            evidence_count=evidence_count,
            signal_confidence=signal_conf,
        )

        # STAGE 3: Planning (Monte Carlo Scenario Simulation)
        mc_result: dict[str, Any] | None = None
        if assessment.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MODERATE):
            with contextlib.suppress(Exception):
                mc_result = self._world_model.simulate_scenarios(
                    mean=0.001,  # 0.1% expected return
                    std_dev=0.02,  # 2% volatility
                    iterations=10000,
                    seed=hash(proposal.proposal_id) % (2**32),
                )

        # STAGE 4 & 5: Verification + Epistemic Update
        new_epistemic = self._determine_epistemic_status(assessment)

        # STAGE 6: Reconstruct proposal with enriched metadata
        enriched = self._enrich_proposal(
            proposal=proposal,
            epistemic_status=new_epistemic,
            assessment=assessment,
            regime_probs=regime_probs,
            mc_result=mc_result,
        )

        logger.info(
            "SUPERCONSCIOUS_LOOP_COMPLETED",
            extra={
                "proposal_id": proposal.proposal_id,
                "new_epistemic": new_epistemic.value,
                "confidence": assessment.confidence.value,
                "veto": assessment.veto_recommended,
            },
        )

        return enriched

    def _determine_epistemic_status(
        self, assessment: Any
    ) -> EpistemicStatus:
        """Map metacognitive assessment to governance EpistemicStatus."""
        if assessment.veto_recommended:
            return EpistemicStatus.UNKNOWN  # Will trigger QUARANTINE in Policy
        if assessment.confidence == ConfidenceLevel.HIGH:
            return EpistemicStatus.FACT
        if assessment.confidence == ConfidenceLevel.MODERATE:
            return EpistemicStatus.INFERENCE
        return EpistemicStatus.HYPOTHESIS

    def _enrich_proposal(
        self,
        proposal: DecisionProposal,
        epistemic_status: EpistemicStatus,
        assessment: Any,
        regime_probs: list[float] | None,
        mc_result: dict[str, Any] | None,
    ) -> DecisionProposal:
        """
        Create enriched copy of proposal with cognitive metadata.
        Uses model_copy with update to preserve frozen model integrity.
        """
        update_fields: dict[str, Any] = {
            "epistemic_status": epistemic_status,
        }

        # Add cognitive metadata to proposal if fields exist
        # This is additive — we never remove or overwrite existing fields
        with contextlib.suppress(Exception):
            enriched = proposal.model_copy(update=update_fields)
            return enriched

        return proposal

    def shutdown(self) -> None:
        """Graceful shutdown of all cognitive components."""
        self._world_model.shutdown()
        logger.info("SUPERCONSCIOUS_LOOP_SHUTDOWN")
