"""
Decision Dispatcher for Atlas AI Control Plane.
Listens to Policy Evaluator outcomes, filters approved decisions,
translates them into Execution Directives, and publishes via NATS.
Contains ZERO business logic or trading decisions.
Governed by: ATLAS Protocol Rule 12 (Minimal Blast Radius).
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from intelligence.agent_control_plane.policy.decision_evaluator import (
    PolicyDecision,
)
from intelligence.contracts.execution_directive import (
    ExecutionDirective,
    MarketContextUpdate,
)
from intelligence.contracts.risk_evaluation_directive import (
    RiskEvaluationDirective,
)
from intelligence.contracts.unified_decision_proposal import (
    DecisionProposal,
    EpistemicStatus,
)
from intelligence.integration_bridge.nats_publisher import NATSPublisher

logger = logging.getLogger(__name__)

STRATEGY_TOPIC = "atlas.strategy.execute.v1"
MARKET_TOPIC = "atlas.market.context.v1"
RISK_TOPIC = "atlas.risk.evaluate.v1"

_ACTION_TO_DIRECTIVE: dict[str, str] = {
    "BUY_SIGNAL": "EXECUTE_LONG",
    "SELL_SIGNAL": "EXECUTE_SHORT",
    "CLOSE": "CLOSE_POSITION",
    "HOLD": "HOLD_POSITION",
    "INVESTIGATE": "UPDATE_CONTEXT",
}


async def dispatch_approved_decision(
    proposal: DecisionProposal,
    decision: PolicyDecision,
    publisher: NATSPublisher,
) -> bool:
    """
    Evaluate policy decision and route approved proposals to downstream agents.

    Args:
        proposal: The fully validated and stressed DecisionProposal.
        decision: The outcome from PolicyEvaluator.
        publisher: Connected NATSPublisher instance.

    Returns:
        True if dispatched successfully or correctly filtered, False on error.
    """
    if decision != PolicyDecision.ALLOW:
        logger.info(
            "DISPATCH_FILTERED",
            extra={
                "proposal_id": proposal.proposal_id,
                "decision": decision.value,
                "reason": "not_authorized_for_execution",
            },
        )
        return True

    ts_ns = int(datetime.now(UTC).timestamp() * 1e9)
    directive_id = str(uuid.uuid4())
    symbol_parts = proposal.target_strategy.split("_")
    symbol = symbol_parts[-1].upper() if len(symbol_parts) > 1 else "UNKNOWN"

    try:
        if proposal.proposed_action in _ACTION_TO_DIRECTIVE:
            directive = ExecutionDirective(
                directive_id=directive_id,
                source_proposal_id=proposal.proposal_id,
                target_agent_family="STRATEGY",
                action=_ACTION_TO_DIRECTIVE[proposal.proposed_action],  # type: ignore[arg-type]
                symbol=symbol,
                final_confidence_score=proposal.confidence_vector.evidence_quality,
                payload=proposal.payload,
                trace_id=proposal.audit_log_ref,
                timestamp_ns=ts_ns,
                audit_log_ref=proposal.audit_log_ref,
            )
            envelope = directive.model_dump_json().encode("utf-8")
            published = await publisher.publish(envelope, topic=STRATEGY_TOPIC)
            if published:
                logger.info(
                    "DIRECTIVE_DISPATCHED",
                    extra={"directive_id": directive_id, "topic": STRATEGY_TOPIC},
                )

        elif proposal.epistemic_status in (EpistemicStatus.INFERENCE, EpistemicStatus.HYPOTHESIS):
            context_update = MarketContextUpdate(
                update_id=directive_id,
                source_proposal_id=proposal.proposal_id,
                symbol=symbol,
                detected_regime="UNKNOWN",
                epistemic_status=proposal.epistemic_status.value,
                confidence_score=proposal.confidence_vector.regime_compatibility,
                reasoning_summary=str(proposal.payload.get("original_reasoning", "")),
                trace_id=proposal.audit_log_ref,
                timestamp_ns=ts_ns,
            )
            envelope = context_update.model_dump_json().encode("utf-8")
            published = await publisher.publish(envelope, topic=MARKET_TOPIC)
            if published:
                logger.info(
                    "CONTEXT_DISPATCHED",
                    extra={"update_id": directive_id, "topic": MARKET_TOPIC},
                )

        else:
            logger.warning(
                "DISPATCH_UNROUTABLE",
                extra={"proposal_id": proposal.proposal_id, "action": proposal.proposed_action},
            )

        risk_directive = RiskEvaluationDirective(
            directive_id=str(uuid.uuid4()),
            source_proposal_id=proposal.proposal_id,
            symbol=symbol,
            proposed_action=proposal.proposed_action,
            confidence_score=proposal.confidence_vector.evidence_quality,
            adversarial_survival_score=proposal.adversarial_report.survival_score,
            regime_compatibility=proposal.confidence_vector.regime_compatibility,
            requires_human_approval=proposal.requires_human_approval,
            trace_id=proposal.audit_log_ref,
            timestamp_ns=ts_ns,
            audit_log_ref=proposal.audit_log_ref,
        )
        risk_envelope = risk_directive.model_dump_json().encode("utf-8")
        risk_published = await publisher.publish(risk_envelope, topic=RISK_TOPIC)
        if risk_published:
            logger.info(
                "RISK_DIRECTIVE_DISPATCHED",
                extra={"directive_id": risk_directive.directive_id, "topic": RISK_TOPIC},
            )

        return True

    except Exception as e:
        logger.error(
            "DISPATCH_FAILED",
            extra={"proposal_id": proposal.proposal_id, "error": str(e)},
        )
        return False
