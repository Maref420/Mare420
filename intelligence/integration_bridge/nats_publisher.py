"""
NATS Publisher for Atlas AI Trading Intelligence Fabric.
Publishes DecisionProposal envelopes to the Go Message Broker via NATS.
Contains ZERO business logic or trading decisions.
Governed by: ATLAS Protocol Rule 16 (Observability) & Rule 12 (Minimal Blast Radius).
"""
from __future__ import annotations

import logging

import nats
from nats.aio.client import Client as NATSClient
from nats.errors import ConnectionClosedError, NoServersError, TimeoutError

logger = logging.getLogger(__name__)

DEFAULT_NATS_URL = "nats://localhost:4222"
DEFAULT_TOPIC = "atlas.control.decision.v1"
PUBLISH_TIMEOUT_SEC = 2


class NATSPublisher:
    """
    Async publisher that transports validated envelopes from Python AI
    to the Go Message Broker via NATS Event Bus.
    """

    def __init__(self, nats_url: str = DEFAULT_NATS_URL) -> None:
        self._nats_url = nats_url
        self._nc: NATSClient | None = None

    async def connect(self) -> bool:
        """Establish connection to NATS server."""
        try:
            self._nc = await nats.connect(
                self._nats_url,
                name="atlas-python-publisher",
                max_reconnect_attempts=3,
                reconnect_time_wait=1.0,
            )
            logger.info(
                "NATS_CONNECTED",
                extra={"url": self._nats_url, "client_id": self._nc.client_id},
            )
            return True
        except (NoServersError, TimeoutError, OSError) as e:
            logger.error(
                "NATS_CONNECTION_FAILED",
                extra={"url": self._nats_url, "error": str(e)},
            )
            return False

    async def publish(
        self,
        envelope_bytes: bytes,
        topic: str = DEFAULT_TOPIC,
    ) -> bool:
        """
        Publish a serialized envelope to NATS.

        Args:
            envelope_bytes: UTF-8 encoded JSON envelope from EnvelopeAdapter.
            topic: Target NATS subject matching Go Broker routing expectations.

        Returns:
            True if published successfully, False otherwise.
        """
        if self._nc is None or self._nc.is_closed:
            logger.warning("NATS_PUBLISH_SKIPPED", extra={"reason": "not_connected"})
            return False

        try:
            await self._nc.publish(topic, envelope_bytes)
            await self._nc.flush(timeout=PUBLISH_TIMEOUT_SEC)

            logger.info(
                "ENVELOPE_PUBLISHED",
                extra={
                    "topic": topic,
                    "size_bytes": len(envelope_bytes),
                    "status": "success",
                },
            )
            return True

        except ConnectionClosedError:
            logger.error(
                "NATS_PUBLISH_FAILED",
                extra={"topic": topic, "error": "connection_closed"},
            )
            return False
        except TimeoutError:
            logger.error(
                "NATS_PUBLISH_FAILED",
                extra={"topic": topic, "error": "flush_timeout"},
            )
            return False
        except Exception as e:
            logger.error(
                "NATS_PUBLISH_FAILED",
                extra={"topic": topic, "error": str(e)},
            )
            return False

    async def close(self) -> None:
        """Gracefully close NATS connection."""
        if self._nc is not None and not self._nc.is_closed:
            await self._nc.drain()
            logger.info("NATS_DISCONNECTED", extra={"url": self._nats_url})
