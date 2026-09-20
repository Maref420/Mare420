"""
World Model — Constructs mathematical representation of market state.
Uses Rust prob_algebra via IPC for Markov Chain regime prediction.

Governed by:
- CG-2: Algebraic Grounding (all models verified by Rust)
- TC-1: Strict Hemispheric Isolation (IPC only, no FFI)
- Rule 12: Minimal Blast Radius (additive module)
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from intelligence.neural_cortex.ipc_client import IpcClient

logger = logging.getLogger(__name__)


class WorldModel:
    """
    Predicts next market regime using algebraic probability engine.
    Translates raw market signals into probabilistic state transitions.
    """

    def __init__(
        self, ipc_socket: str = "/app/uds/atlas-ipc.sock"
    ) -> None:
        self._ipc = IpcClient(socket_path=ipc_socket)
        self._connected = False

    def _ensure_connection(self) -> bool:
        """Lazy connect to IPC server."""
        if not self._connected:
            self._connected = self._ipc.connect()
        return self._connected

    def predict_regime(
        self,
        transition_matrix: list[float],
        current_state: int,
        states_count: int,
    ) -> dict[str, Any] | None:
        """
        Predict next market regime probabilities via Markov Chain.

        Args:
            transition_matrix: Flat list of state transition probabilities.
            current_state: Index of current market regime.
            states_count: Total number of possible regimes.

        Returns:
            Dictionary with next_state_probabilities or None on failure.
        """
        if not self._ensure_connection():
            logger.warning("WORLD_MODEL_IPC_UNAVAILABLE")
            return None

        request_id = f"wm-{uuid.uuid4().hex[:8]}"
        payload = {
            "request_type": "prob_algebra",
            "request_id": request_id,
            "operation": "markov_transition",
            "parameters": {
                "states": states_count,
                "transition_matrix": transition_matrix,
                "current_state": current_state,
            },
        }

        response = self._ipc.send_request(payload)

        if response is None or not response.get("success"):
            error_msg = response.get("error", "unknown") if response else "no_response"
            logger.error(
                "WORLD_MODEL_PREDICTION_FAILED",
                extra={"request_id": request_id, "error": error_msg},
            )
            return None

        result = response.get("result")
        logger.info(
            "WORLD_MODEL_REGIME_PREDICTED",
            extra={
                "request_id": request_id,
                "probabilities": result.get("next_state_probabilities") if isinstance(result, dict) else [],
            },
        )
        return result if isinstance(result, dict) else None

    def simulate_scenarios(
        self,
        mean: float,
        std_dev: float,
        iterations: int = 10000,
        seed: int = 42,
    ) -> dict[str, Any] | None:
        """
        Run Monte Carlo simulation for scenario planning.
        Capped at 1M iterations per Rust safety constraint.

        Args:
            mean: Expected return mean.
            std_dev: Return volatility.
            iterations: Number of simulation paths.
            seed: Deterministic RNG seed for reproducibility.

        Returns:
            Simulation statistics (mean_result, min, max) or None.
        """
        if not self._ensure_connection():
            logger.warning("WORLD_MODEL_IPC_UNAVAILABLE")
            return None

        request_id = f"mc-{uuid.uuid4().hex[:8]}"
        payload = {
            "request_type": "prob_algebra",
            "request_id": request_id,
            "operation": "monte_carlo_sim",
            "parameters": {
                "iterations": min(iterations, 1_000_000),
                "mean": mean,
                "std_dev": std_dev,
                "seed": seed,
            },
        }

        response = self._ipc.send_request(payload)

        if response is None or not response.get("success"):
            logger.error(
                "WORLD_MODEL_SIMULATION_FAILED",
                extra={"request_id": request_id},
            )
            return None

        result = response.get("result")
        logger.info(
            "WORLD_MODEL_SIMULATION_COMPLETE",
            extra={"request_id": request_id, "iterations": iterations},
        )
        return result if isinstance(result, dict) else None

    def shutdown(self) -> None:
        """Gracefully close IPC connection."""
        self._ipc.disconnect()
        self._connected = False
