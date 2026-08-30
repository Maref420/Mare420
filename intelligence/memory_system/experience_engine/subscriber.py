"""Memory Event Subscriber: Receive events from Go Broker and route to ExperienceEngine.

Governed by:
- contracts/schemas/memory/memory-experience-event-v1.json
- Architecture Review: ARCH-REVIEW-002

Current transport: HTTP polling (stdlib only, no new dependencies).
Future upgrade path: NATS (approved_future in dependencies registry).
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError
import json

from intelligence.memory_system.experience_engine.engine import ExperienceEngine

logger = logging.getLogger(__name__)


class MemoryEventSubscriber:
    """Poll Go Broker for memory experience events and route to ExperienceEngine."""

    def __init__(
        self,
        engine: ExperienceEngine,
        broker_url: str,
        agent_id: str,
    ) -> None:
        self._engine = engine
        self._broker_url = broker_url.rstrip("/")
        self._agent_id = agent_id

    def poll_once(self) -> int:
        """Poll broker once, process all received events.

        Returns number of successfully processed events.
        Logs errors but never raises — resilient to broker failures.
        """
        url = f"{self._broker_url}/subscribe?topic=memory.experience.v1"
        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=5) as resp:
                body = resp.read().decode("utf-8")
        except URLError as exc:
            logger.warning("Broker poll failed: %s", exc)
            return 0
        except Exception as exc:
            logger.warning("Broker poll unexpected error: %s", exc)
            return 0

        try:
            messages: list[dict[str, Any]] = json.loads(body)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON from broker: %s", exc)
            return 0

        processed = 0
        for msg in messages:
            try:
                self._process_message(msg)
                processed += 1
            except Exception as exc:
                logger.warning("Failed to process memory event: %s", exc)
        return processed

    def _process_message(self, msg: dict[str, Any]) -> None:
        """Parse and route a single memory experience event."""
        payload = msg.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("message payload is not a dict")

        event_type = self._detect_event_type(payload)
        operation_id = msg.get("metadata", {}).get("specification_id", "unknown")

        if event_type == "execution_outcome":
            self._engine.capture_execution_outcome(
                order_id=payload["order_id"],
                symbol=payload["symbol"],
                side=payload["side"],
                quantity=float(payload["quantity"]),
                pnl=float(payload["pnl"]),
                status=payload["status"],
                agent_id=self._agent_id,
                operation_id=operation_id,
            )
        elif event_type == "risk_assessment":
            self._engine.capture_risk_assessment(
                assessment_type=payload["assessment_type"],
                result=payload["result"],
                circuit_breaker_state=payload["circuit_breaker_state"],
                risk_score=float(payload["risk_score"]),
                agent_id=self._agent_id,
                operation_id=operation_id,
            )
        elif event_type == "agent_decision":
            self._engine.capture_agent_decision(
                decision_type=payload["decision_type"],
                input_summary=payload["input_summary"],
                output_action=payload["output_action"],
                confidence=float(payload["confidence"]),
                agent_id=self._agent_id,
                operation_id=operation_id,
            )
        else:
            raise ValueError(f"unknown memory event type: {event_type}")

    @staticmethod
    def _detect_event_type(payload: dict[str, Any]) -> str:
        """Detect event type from payload field presence."""
        if "order_id" in payload:
            return "execution_outcome"
        if "assessment_type" in payload:
            return "risk_assessment"
        if "decision_type" in payload:
            return "agent_decision"
        return "unknown"
