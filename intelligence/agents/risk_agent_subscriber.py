"""
Concrete Risk Agent Subscriber.
Demonstrates how downstream risk agents consume RiskEvaluationDirectives from NATS.
Contains ZERO modifications to existing agent code.
Governed by: Event-Driven Isolation & Immutable Contracts.
"""
from __future__ import annotations

import logging
from typing import Any

from intelligence.contracts.risk_evaluation_directive import RiskEvaluationDirective
from intelligence.integration_bridge.agent_subscriber import AgentSubscriber

logger = logging.getLogger(__name__)


class RiskAgentSubscriber(AgentSubscriber):
    """
    Concrete implementation for Risk Agents.
    Validates incoming messages against RiskEvaluationDirective schema
    before any processing occurs.
    """

    def __init__(self, nats_url: str = "nats://localhost:4222") -> None:
        super().__init__(
            nats_url=nats_url,
            topic="atlas.risk.evaluate.v1",
            agent_id="risk-agent-01",
        )

    async def handle_message(self, payload: dict[str, Any], trace_id: str) -> None:
        """
        Process validated RiskEvaluationDirective.

        Args:
            payload: Dictionary representation of the directive.
            trace_id: Trace identifier for audit logging.
        """
        # Gate: Strict schema validation before any business logic
        directive = RiskEvaluationDirective(**payload)

        logger.info(
            "RISK_DIRECTIVE_RECEIVED",
            extra={
                "agent_id": self._agent_id,
                "directive_id": directive.directive_id,
                "symbol": directive.symbol,
                "action": directive.proposed_action,
                "confidence": directive.confidence_score,
                "survival": directive.adversarial_survival_score,
                "human_approval": directive.requires_human_approval,
                "trace_id": trace_id,
            },
        )

        # Business Logic Placeholder
        # In production, this would calculate position sizing or reject high-risk trades
        if directive.adversarial_survival_score < 0.6:
            logger.warning(
                "RISK_ALERT_HIGH_RISK",
                extra={
                    "symbol": directive.symbol,
                    "survival_score": directive.adversarial_survival_score,
                    "action": "REDUCE_POSITION_SIZE",
                },
            )
        else:
            logger.info(
                "RISK_CLEARED",
                extra={
                    "symbol": directive.symbol,
                    "confidence": directive.confidence_score,
                    "action": "PROCEED_TO_EXECUTION",
                },
            )
