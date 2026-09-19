"""
Envelope Adapter for Cross-Language Transport.
Wraps Unified Decision Proposals into the standard EngineMessage envelope
expected by the Go Message Broker validator.
Contains ZERO business logic.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from intelligence.contracts.unified_decision_proposal import DecisionProposal


def wrap_decision_proposal(
    proposal: DecisionProposal,
    source_engine: str = "python_ai",
) -> bytes:
    """
    Produce an EngineMessage envelope matching Go validator expectations.

    Args:
        proposal: The validated DecisionProposal instance.
        source_engine: Identifier for the producing engine.

    Returns:
        UTF-8 encoded JSON bytes ready for Go Message Broker transport.
    """
    envelope: dict[str, Any] = {
        "contract_version": "1.0",
        "message_type": "decision-proposal-v1",
        "source_engine": source_engine,
        "timestamp": datetime.now(UTC).isoformat(),
        "payload": json.loads(proposal.to_json()),
        "metadata": {
            "specification_id": "unified-decision-proposal-v1",
            "policy_version": "1.0",
            "owner": "Python AI Layer",
            "validation_status": "pending_control_plane",
        },
    }
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")
