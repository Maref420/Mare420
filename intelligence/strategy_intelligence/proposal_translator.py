"""
Proposal Translator — Bridges ConfluenceResult to DecisionProposal.

Converts the output of ConfluenceMatrix into a schema-compliant
DecisionProposal that can be processed by SuperconsciousLoop.

Governed by:
- Rule 12: Minimal Blast Radius (additive only)
- SE-1: No Single Strategy Execution (confluence already enforced)
- CG-3: Audit Every Thought (translation reasoning logged)
- Rule 10: Immutable Contracts (frozen models throughout)
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from intelligence.strategy_intelligence.confluence import ConfluenceResult
from intelligence.strategy_intelligence.strategy_evaluator.models import (
    Direction,
)

logger = logging.getLogger(__name__)


class ProposalTranslator:
    """
    Translates ConfluenceResult into DecisionProposal-compatible fields.

    This is a pure translation layer — it does NOT make decisions.
    It maps confluence data into the format expected by the
    Superconscious Loop and Policy Evaluator.

    Governed by TC-1: No I/O, no side effects, pure function.
    """

    @staticmethod
    def translate(
        confluence: ConfluenceResult,
        source_trace_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Translate ConfluenceResult to DecisionProposal field dictionary.

        Returns a dictionary (not a DecisionProposal instance) because
        DecisionProposal construction requires fields that may come from
        other pipeline stages. The orchestrator merges this dict with
        other data before creating the final proposal.

        Args:
            confluence: Frozen ConfluenceResult from ConfluenceMatrix.
            source_trace_id: Optional trace ID for audit trail.

        Returns:
            Dictionary of fields ready for DecisionProposal construction.
        """
        trace_id = source_trace_id or str(uuid.uuid4())

        # Map direction to action string
        action = ProposalTranslator._direction_to_action(confluence.direction)

        # Build confidence vector components from confluence scores
        # Rule 7: Multi-dimensional trust metric — no single scalar
        confidence_components = ProposalTranslator._build_confidence_components(
            confluence
        )

        # Determine initial epistemic status based on actionability
        # CG-1: No Action Without Reflection
        epistemic = ProposalTranslator._determine_initial_epistemic(confluence)

        # Build evidence references from dominant strategies
        evidence_refs = [
            f"strategy:{s}" for s in confluence.dominant_strategies
        ]

        result = {
            "proposal_id": str(uuid.uuid4()),
            "trace_id": trace_id,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "source_agent": "confluence_matrix",
            "proposed_action": action,
            "symbol": confluence.symbol,
            "epistemic_status": epistemic,
            "confidence_components": confidence_components,
            "evidence_refs": evidence_refs,
            "aligned_strategy_count": confluence.aligned_strategy_count,
            "regime": confluence.regime.value,
            "is_actionable": confluence.is_actionable,
            "confluence_score": confluence.confluence_score,
            "metadata": {
                "long_weighted_confidence": confluence.long_weighted_confidence,
                "short_weighted_confidence": confluence.short_weighted_confidence,
                "total_strategies": confluence.total_strategy_count,
                "details": confluence.details,
            },
        }

        logger.info(
            "PROPOSAL_TRANSLATED",
            extra={
                "proposal_id": result["proposal_id"],
                "trace_id": trace_id,
                "action": action,
                "epistemic": epistemic,
                "confluence_score": confluence.confluence_score,
                "is_actionable": confluence.is_actionable,
                "aligned_count": confluence.aligned_strategy_count,
            },
        )

        return result

    @staticmethod
    def _direction_to_action(direction: Direction) -> str:
        """Map Direction enum to action string."""
        if direction == Direction.LONG:
            return "BUY"
        if direction == Direction.SHORT:
            return "SELL"
        return "HOLD"

    @staticmethod
    def _build_confidence_components(
        confluence: ConfluenceResult,
    ) -> dict[str, float]:
        """
        Build multi-dimensional confidence components per Rule 7.

        Maps confluence metrics to the 6 dimensions expected by
        ConfidenceVector in DecisionProposal.
        """
        score = confluence.confluence_score
        aligned = confluence.aligned_strategy_count
        total = max(confluence.total_strategy_count, 1)

        return {
            "evidence_quality": min(1.0, aligned / 3.0),
            "source_reliability": score,
            "data_freshness": 1.0,  # Real-time from WS ingestion
            "cross_validation": min(1.0, aligned / 2.0),
            "historical_accuracy": score * 0.8,  # Discounted until G6 training
            "regime_compatibility": min(1.0, float(aligned) / float(total)),
        }

    @staticmethod
    def _determine_initial_epistemic(confluence: ConfluenceResult) -> str:
        """
        Determine initial epistemic status before Superconscious processing.

        Governed by Rule 2 (Anti-Hallucination):
        - UNKNOWN must never map directly to FACT
        - Non-actionable starts as HYPOTHESIS
        - Actionable with high confidence starts as INFERENCE
        - Superconscious Loop will elevate or downgrade
        """
        if not confluence.is_actionable:
            return "HYPOTHESIS"
        if confluence.confluence_score >= 0.7 and confluence.aligned_strategy_count >= 3:
            return "INFERENCE"
        return "HYPOTHESIS"
