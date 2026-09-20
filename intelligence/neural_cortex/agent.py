"""
Neural Cortex Agent — Left Hemisphere of Tri-Cortex Architecture.
Subscribes to neural computation requests via NATS, routes heavy
algebraic work to Rust IPC Server, and publishes fused results.

Governed by:
- ATLAS Protocol Rule 12 (Minimal Blast Radius)
- TC-1: Strict Hemispheric Isolation
- TC-3: Shared Memory Integration
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from intelligence.integration_bridge.agent_subscriber import AgentSubscriber
from intelligence.neural_cortex.ipc_client import IpcClient

logger = logging.getLogger(__name__)


class NeuralRequest(BaseModel):
    """Validated schema for incoming neural computation requests."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(..., min_length=1)
    operation: str = Field(..., min_length=1)
    symbol: str = Field(default="UNKNOWN")
    parameters: dict[str, Any] = Field(default_factory=dict)


class NeuralCortexAgent(AgentSubscriber):
    """
    Concrete NATS subscriber that bridges Python neural orchestration
    with Rust algebraic compute via UDS IPC binary protocol.

    Data flow:
        NATS topic → Validate → IPC UDS → Rust prob_algebra → Response → NATS
    """

    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        topic: str = "atlas.neural.request.v1",
        ipc_socket: str = "/app/uds/atlas-ipc.sock",
    ) -> None:
        super().__init__(
            nats_url=nats_url,
            topic=topic,
            agent_id="neural-cortex-agent",
        )
        self._ipc = IpcClient(socket_path=ipc_socket)
        self._connected = False

    async def handle_message(
        self, payload: dict[str, Any], trace_id: str
    ) -> None:
        """
        Process neural request: validate, route to Rust IPC, log result.
        """
        try:
            request = NeuralRequest(**payload)
        except ValidationError as e:
            logger.error(
                "NEURAL_REQUEST_VALIDATION_FAILED",
                extra={"trace_id": trace_id, "error": str(e)},
            )
            return

        logger.info(
            "NEURAL_REQUEST_RECEIVED",
            extra={
                "request_id": request.request_id,
                "operation": request.operation,
                "symbol": request.symbol,
                "trace_id": trace_id,
            },
        )

        # Ensure IPC connection
        if not self._connected:
            self._connected = self._ipc.connect()

        if not self._connected:
            logger.warning(
                "NEURAL_IPC_UNAVAILABLE",
                extra={"request_id": request.request_id},
            )
            return

        # Build IPC request matching Rust AlgebraRequest structure
        ipc_payload = {
            "request_type": "prob_algebra",
            "request_id": request.request_id,
            "operation": request.operation,
            "parameters": request.parameters,
        }

        # Send via binary length-prefixed UDS protocol
        response = self._ipc.send_request(ipc_payload)

        if response is None:
            logger.error(
                "NEURAL_IPC_REQUEST_FAILED",
                extra={"request_id": request.request_id},
            )
            return

        success = response.get("success", False)
        if success:
            logger.info(
                "NEURAL_ALGEBRA_RESULT",
                extra={
                    "request_id": request.request_id,
                    "operation": request.operation,
                    "result_keys": list(response.get("result", {}).keys())
                    if isinstance(response.get("result"), dict)
                    else [],
                },
            )
        else:
            logger.warning(
                "NEURAL_ALGEBRA_ERROR",
                extra={
                    "request_id": request.request_id,
                    "error": response.get("error", "unknown"),
                },
            )

    def shutdown(self) -> None:
        """Gracefully close IPC connection."""
        self._ipc.disconnect()
        self._connected = False
        logger.info("NEURAL_CORTEX_SHUTDOWN")
