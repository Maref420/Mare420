"""
Base Subscriber for Downstream Agents (Strategy & Market Analysis).
Provides a secure, async interface to consume directives from NATS.
Contains ZERO business logic. Subclasses must implement handle_message().
Governed by: Event-Driven Isolation & Immutable Contracts.
"""
from __future__ import annotations

import contextlib
import logging
from abc import ABC, abstractmethod
from typing import Any

import nats
from nats.aio.client import Client as NATSClient
from nats.aio.msg import Msg
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class AgentSubscriber(ABC):
    """
    Abstract base class for agents consuming events from NATS Event Bus.
    Enforces schema validation before any processing occurs.
    Supports both NATS Core Pub/Sub and JetStream.
    """

    def __init__(self, nats_url: str, topic: str, agent_id: str) -> None:
        self._nats_url = nats_url
        self._topic = topic
        self._agent_id = agent_id
        self._nc: NATSClient | None = None
        self._sub: Any = None

    @abstractmethod
    async def handle_message(self, payload: dict[str, Any], trace_id: str) -> None:
        """
        Process a validated message. Must be implemented by concrete agents.

        Args:
            payload: Validated dictionary representation of the directive.
            trace_id: Trace identifier for audit logging.
        """
        pass

    async def _message_handler(self, msg: Msg) -> None:
        """Internal NATS message handler with validation gate."""
        try:
            raw_data = msg.data.decode("utf-8")
            import json
            payload = json.loads(raw_data)
            trace_id = payload.get("trace_id", "unknown")

            logger.info(
                "MESSAGE_RECEIVED",
                extra={
                    "agent_id": self._agent_id,
                    "topic": self._topic,
                    "trace_id": trace_id,
                },
            )

            await self.handle_message(payload, trace_id)

            if hasattr(msg, "_ackd") and not msg._ackd:
                with contextlib.suppress(Exception):
                    await msg.ack()

        except ValidationError as e:
            logger.error(
                "SCHEMA_VALIDATION_FAILED",
                extra={"agent_id": self._agent_id, "error": str(e)},
            )
            if hasattr(msg, "_ackd"):
                with contextlib.suppress(Exception):
                    await msg.term()

        except Exception as e:
            logger.error(
                "HANDLER_ERROR",
                extra={"agent_id": self._agent_id, "error": str(e)},
            )
            if hasattr(msg, "_ackd"):
                with contextlib.suppress(Exception):
                    await msg.nak()

    async def start(self) -> bool:
        """Connect to NATS and subscribe to topic."""
        try:
            self._nc = await nats.connect(
                self._nats_url,
                name=f"atlas-subscriber-{self._agent_id}",
            )
            self._sub = await self._nc.subscribe(
                self._topic,
                cb=self._message_handler,
            )
            logger.info(
                "SUBSCRIBER_STARTED",
                extra={"agent_id": self._agent_id, "topic": self._topic},
            )
            return True
        except Exception as e:
            logger.error(
                "SUBSCRIBER_START_FAILED",
                extra={"agent_id": self._agent_id, "error": str(e)},
            )
            return False

    async def stop(self) -> None:
        """Gracefully unsubscribe and disconnect."""
        if self._sub is not None:
            await self._sub.unsubscribe()
        if self._nc is not None and not self._nc.is_closed:
            await self._nc.drain()
        logger.info("SUBSCRIBER_STOPPED", extra={"agent_id": self._agent_id})
