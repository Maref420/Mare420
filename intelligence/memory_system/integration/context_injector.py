"""
Memory Context Injector for Atlas AI Control Plane.
Reads historical failures from MemoryKernel and injects them into
DecisionProposal before Policy Evaluation.
Operates synchronously but is designed to be called within async context.
Governed by: Minimal Blast Radius Rule 12 & Read-Before-Decide Principle.
"""
from __future__ import annotations

import logging
from typing import Any

from intelligence.contracts.unified_decision_proposal import DecisionProposal
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel

logger = logging.getLogger(__name__)


def inject_memory_context(
    proposal: DecisionProposal,
    kernel: MemoryKernel,
    max_failures_to_inject: int = 5,
) -> DecisionProposal:
    """
    Query MemoryKernel for historical failures related to this proposal
    and return a new DecisionProposal with updated known_failures field.

    Args:
        proposal: The original frozen DecisionProposal.
        kernel: Initialized MemoryKernel instance.
        max_failures_to_inject: Maximum number of failure records to attach.

    Returns:
        A new DecisionProposal with memory context injected.
    """
    try:
        symbol = proposal.target_strategy.split("_")[-1] if "_" in proposal.target_strategy else "UNKNOWN"
        search_key = f"failure_{symbol}_{proposal.proposed_action}"

        record = kernel.retrieve(search_key)

        failures: list[dict[str, Any]] = []
        if record is not None and record.validation_status.value == "VALIDATED":
            content_data = record.content
            if isinstance(content_data, dict):
                history = content_data.get("failure_history", [])
                failures = history[:max_failures_to_inject]

            if failures:
                logger.info(
                    "MEMORY_CONTEXT_INJECTED",
                    extra={
                        "proposal_id": proposal.proposal_id,
                        "failures_found": len(failures),
                        "symbol": symbol,
                    },
                )

        if not failures:
            return proposal

        prop_dict = proposal.model_dump()
        prop_dict["known_failures_from_memory"] = failures
        enriched_proposal = DecisionProposal(**prop_dict)
        return enriched_proposal

    except Exception as e:
        logger.error(
            "MEMORY_INJECTION_FAILED",
            extra={"proposal_id": proposal.proposal_id, "error": str(e)},
        )
        return proposal
