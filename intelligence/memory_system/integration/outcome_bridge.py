"""
Outcome Bridge Subscriber for Atlas AI Memory Layer.
Bridges NATS Event Bus (atlas.execution.outcome.v1) with ExperienceEngine.
Extends AgentSubscriber ABC for async transport and validation.

Governed by:
- contracts/schemas/memory/memory-experience-event-v1.json
- ATLAS Protocol Rule 12 (Minimal Blast Radius)
- lifecycle-policy.yaml: audit_logging_required: true
- Zero Side Effects on Failure principle
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from intelligence.integration_bridge.agent_subscriber import AgentSubscriber
from intelligence.memory_system.experience_engine.engine import ExperienceEngine

logger = logging.getLogger(__name__)


class ExecutionOutcomeEvent(BaseModel):
    """
    Validated schema for execution outcome events from NATS.
    Maps directly to memory-experience-event-v1.json execution_outcome fields.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    order_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    side: str = Field(..., pattern=r"^(buy|sell)$")
    quantity: float = Field(..., ge=0)
    pnl: float = 0.0
    status: str = Field(
        ...,
        pattern=r"^(filled|rejected|cancelled|halted_by_circuit_breaker)$",
    )
    agent_id: str = Field(default="strategy_agent", min_length=1)
    trace_id: str = Field(default="", min_length=0)


class OutcomeBridgeSubscriber(AgentSubscriber):
    """
    Concrete NATS subscriber that receives execution outcomes and routes
    them through ExperienceEngine into persistent memory storage.

    This is the physical bridge between the Signal Execution layer and
    the Memory Layer. It implements exactly one responsibility:
    receive outcome → validate → capture → store.
    """

    def __init__(
        self,
        experience_engine: ExperienceEngine,
        nats_url: str = "nats://localhost:4222",
        topic: str = "atlas.execution.outcome.v1",
    ) -> None:
        super().__init__(
            nats_url=nats_url,
            topic=topic,
            agent_id="outcome-bridge-subscriber",
        )
        self._engine = experience_engine

    async def handle_message(
        self, payload: dict[str, Any], trace_id: str
    ) -> None:
        """
        Process validated NATS message and persist to memory.

        Governed by:
        - Contract Purity: Pydantic validation before any processing
        - Zero Side Effects: failures logged but never propagated
        - Traceability: operation_id + agent_id always included

        Args:
            payload: Raw dictionary from NATS message.
            trace_id: Trace identifier for audit correlation.
        """
        operation_id = f"outcome-{uuid.uuid4().hex[:8]}"

        try:
            # STEP 1: Schema Validation (Contract Purity)
            event = ExecutionOutcomeEvent(**payload)

            logger.info(
                "OUTCOME_BRIDGE_RECEIVED",
                extra={
                    "order_id": event.order_id,
                    "symbol": event.symbol,
                    "status": event.status,
                    "trace_id": trace_id,
                    "operation_id": operation_id,
                },
            )

            # STEP 2: Route through ExperienceEngine → Kernel → Storage
            record = self._engine.capture_execution_outcome(
                order_id=event.order_id,
                symbol=event.symbol,
                side=event.side,
                quantity=event.quantity,
                pnl=event.pnl,
                status=event.status,
                agent_id=event.agent_id,
                operation_id=operation_id,
                metadata={
                    "trace_id": trace_id,
                    "source_topic": self._topic,
                },
            )

            logger.info(
                "OUTCOME_BRIDGE_PERSISTED",
                extra={
                    "order_id": event.order_id,
                    "memory_id": record.memory_id,
                    "memory_type": record.memory_type.value,
                    "operation_id": operation_id,
                },
            )

        except ValidationError as e:
            logger.error(
                "OUTCOME_BRIDGE_VALIDATION_FAILED",
                extra={
                    "trace_id": trace_id,
                    "operation_id": operation_id,
                    "error": str(e),
                },
            )
        except ValueError as e:
            logger.error(
                "OUTCOME_BRIDGE_CAPTURE_REJECTED",
                extra={
                    "trace_id": trace_id,
                    "operation_id": operation_id,
                    "error": str(e),
                },
            )
        except Exception as e:
            logger.error(
                "OUTCOME_BRIDGE_UNEXPECTED_ERROR",
                extra={
                    "trace_id": trace_id,
                    "operation_id": operation_id,
                    "error": str(e),
                },
            )
