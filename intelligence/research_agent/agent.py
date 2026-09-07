# MODULE: atlas-research-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# ADR: docs/decisions/006-governed-memory-system.md
# WARNING: No bare except. source_uri mandatory. agent_id mandatory.
from __future__ import annotations

import json
import logging
import signal
import time
from typing import Any

from .learning import LearningPackage
from .models import AppError, ExperimentResult, ForensicsSignal, ResearchDecision

logger = logging.getLogger(__name__)


class _StubMemoryStore:
    def append(self, record: dict[str, Any]) -> None:
        logger.info("memory_store_append", extra={"record": json.dumps(record, default=str)})


class ResearchAgent:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.aqs_threshold: int = int(config.get("aqs_threshold", 50))
        self.toxicity_threshold: float = float(config.get("toxicity_threshold", 0.5))
        self.learning = LearningPackage()
        self._memory = _StubMemoryStore()
        self._running: bool = True
        self._setup_signals()

    def _setup_signals(self) -> None:
        try:
            signal.signal(signal.SIGTERM, self._handle_shutdown)
            signal.signal(signal.SIGINT, self._handle_shutdown)
        except (ValueError, OSError):
            logger.warning("signal_setup_skipped")

    def _handle_shutdown(self, signum: int, frame: Any) -> None:
        logger.info("shutdown_signal", extra={"signum": signum})
        self._running = False

    def process_signal(self, raw_json: str, trace_id: str) -> ResearchDecision:
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise AppError("VAL_INVALID_JSON", "Failed to parse JSON", retryable=False) from e

        if not isinstance(payload, dict):
            raise AppError("VAL_INVALID_PAYLOAD", "Payload must be object", retryable=False)

        try:
            sig = ForensicsSignal.model_validate(payload)
        except (ValueError, TypeError) as e:
            raise AppError("VAL_MODEL_ERROR", f"Validation failed: {e}", retryable=False) from e

        if not sig.source_uri:
            raise AppError("VAL_MISSING_SOURCE", "source_uri mandatory per ADR-006", retryable=False)

        boost, matched_ids = self.learning.score_signal(sig)

        if sig.spoofing_detected:
            action = "alert"
            base_confidence = 0.95
        elif sig.aqs_score >= self.aqs_threshold and sig.vpin_toxicity < self.toxicity_threshold:
            action = "investigate"
            base_confidence = sig.confidence + boost
        elif sig.aqs_score < 30:
            action = "ignore"
            base_confidence = 0.5
        else:
            action = "archive"
            base_confidence = 0.3

        final_confidence = round(min(max(base_confidence, 0.0), 1.0), 4)

        reasoning = (
            f"AQS={sig.aqs_score}, toxicity={sig.vpin_toxicity}, "
            f"spoofing={sig.spoofing_detected}, boost={boost}, "
            f"patterns_matched={len(matched_ids)}"
        )

        decision = ResearchDecision(
            symbol=sig.symbol,
            action=action,
            confidence=final_confidence,
            reasoning=reasoning,
            memory_refs=matched_ids,
            trace_id=trace_id,
            timestamp_ms=int(time.time() * 1000),
        )

        self._memory.append({
            "trace_id": trace_id,
            "action": action,
            "symbol": sig.symbol,
            "agent_id": "research_agent",
            "source_uri": sig.source_uri,
        })

        logger.info("decision_made", extra={
            "trace_id": trace_id,
            "action": action,
            "confidence": final_confidence,
            "symbol": sig.symbol,
        })

        return decision

    def learn_from_outcome(self, result: ExperimentResult) -> None:
        self.learning.record_experiment(result)
        logger.info("learning_updated", extra={
            "experiment_id": result.experiment_id,
            "pattern_id": result.pattern_id,
        })

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "agent_id": "research_agent",
            "pattern_count": len(self.learning._patterns),
            "timestamp_ms": int(time.time() * 1000),
        }
