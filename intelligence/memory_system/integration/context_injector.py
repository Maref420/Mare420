"""
Multi-Tier Memory Context Injector for Atlas AI Control Plane.
Reads from Working, Episodic, Semantic, and Procedural memory tiers
and injects consolidated context into DecisionProposal before Policy Evaluation.

Governed by:
- Minimal Blast Radius Rule 12
- Read-Before-Decide Principle
- lifecycle-policy.yaml: operations.retrieve.kernel_required: true
"""
from __future__ import annotations

import logging
from typing import Any

from intelligence.contracts.unified_decision_proposal import DecisionProposal
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import MemoryType

logger = logging.getLogger(__name__)


def inject_memory_context(
    proposal: DecisionProposal,
    kernel: MemoryKernel,
    max_records_per_tier: int = 3,
) -> DecisionProposal:
    """
    Query MemoryKernel across all memory tiers for context related to this
    proposal and return a new DecisionProposal with enriched context.

    Reads from:
    - WORKING: Active/duplicate signal detection
    - EPISODIC: Recent execution outcomes for same symbol/action
    - SEMANTIC: Consolidated knowledge rules
    - PROCEDURAL: Learned execution methods

    Args:
        proposal: The original frozen DecisionProposal.
        kernel: Initialized MemoryKernel instance.
        max_records_per_tier: Maximum records to inject per memory tier.

    Returns:
        A new DecisionProposal with multi-tier memory context injected.
    """
    try:
        symbol = (
            proposal.target_strategy.split("_")[-1]
            if "_" in proposal.target_strategy
            else "UNKNOWN"
        )
        action = proposal.proposed_action

        context_payload: dict[str, Any] = {
            "working_signals": [],
            "episodic_outcomes": [],
            "semantic_knowledge": [],
            "procedural_methods": [],
        }

        # Tier 1: Working Memory (exact key match for active signals)
        working_key = f"working_{symbol}_{action}"
        working_record = kernel.retrieve(working_key)
        if (
            working_record is not None
            and working_record.memory_type == MemoryType.WORKING
            and working_record.validation_status.value == "VALIDATED"
        ):
            context_payload["working_signals"].append(
                {"id": working_record.memory_id, "content": working_record.content}
            )

        # Tier 2: Episodic Memory (recent outcomes)
        episodic_key = f"episodic_{symbol}_{action}"
        episodic_record = kernel.retrieve(episodic_key)
        if (
            episodic_record is not None
            and episodic_record.memory_type == MemoryType.EPISODIC
            and episodic_record.validation_status.value == "VALIDATED"
        ):
            content = episodic_record.content
            if isinstance(content, dict):
                context_payload["episodic_outcomes"].append(
                    {
                        "order_id": content.get("order_id", ""),
                        "status": content.get("status", ""),
                        "pnl": content.get("pnl", 0.0),
                    }
                )

        # Tier 3: Semantic Memory (consolidated knowledge)
        semantic_key = f"semantic:episodic_{symbol}_{action}"
        semantic_record = kernel.retrieve(semantic_key)
        if (
            semantic_record is not None
            and semantic_record.memory_type == MemoryType.SEMANTIC
            and semantic_record.validation_status.value == "VALIDATED"
        ):
            content = semantic_record.content
            if isinstance(content, dict):
                context_payload["semantic_knowledge"].append(
                    content.get("knowledge", {})
                )

        # Tier 4: Procedural Memory (learned methods)
        procedural_key = f"procedural_{symbol}_{action}"
        procedural_record = kernel.retrieve(procedural_key)
        if (
            procedural_record is not None
            and procedural_record.memory_type == MemoryType.PROCEDURAL
            and procedural_record.validation_status.value == "VALIDATED"
        ):
            context_payload["procedural_methods"].append(
                {"id": procedural_record.memory_id, "content": procedural_record.content}
            )

        # Check if any context was found
        has_context = any(len(v) > 0 for v in context_payload.values())

        if not has_context:
            return proposal

        total_records = sum(len(v) for v in context_payload.values())
        logger.info(
            "MULTI_TIER_CONTEXT_INJECTED",
            extra={
                "proposal_id": proposal.proposal_id,
                "symbol": symbol,
                "action": action,
                "total_records": total_records,
                "tiers_hit": [k for k, v in context_payload.items() if v],
            },
        )

        prop_dict = proposal.model_dump()
        prop_dict["memory_context"] = context_payload
        enriched_proposal = DecisionProposal(**prop_dict)
        return enriched_proposal

    except Exception as e:
        logger.error(
            "MULTI_TIER_INJECTION_FAILED",
            extra={"proposal_id": proposal.proposal_id, "error": str(e)},
        )
        return proposal
