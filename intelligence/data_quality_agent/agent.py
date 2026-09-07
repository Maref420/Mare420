# MODULE: atlas-data-quality-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# ADR: docs/decisions/006-governed-memory-system.md
# CONTRACT: ErrorEnvelope codes — VAL_INVALID_JSON, VAL_MODEL_ERROR, VAL_MISSING_SOURCE
# WARNING: No bare except. No floats. source_uri mandatory.
from __future__ import annotations

import json
import logging
import signal
import time
from typing import Any

from .anomaly import AnomalyDetector
from .models import AnomalyAlert, AppError, SpreadSignal

logger = logging.getLogger(__name__)


class _StubMemoryStore:
    """Placeholder until GovernedMemoryStore wired per ADR-006 Phase 2."""

    def append(self, record: dict[str, Any]) -> None:
        logger.info("memory_store_append", extra={"record": json.dumps(record, default=str)})


class DataQualityAgent:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.spread_threshold_bps = int(config.get("spread_threshold_bps", 50))
        self.stale_threshold_ms = int(config.get("stale_threshold_ms", 5000))
        self.min_sources = int(config.get("min_sources", 2))
        self.detector = AnomalyDetector(
            spread_threshold_bps=self.spread_threshold_bps,
            stale_threshold_ms=self.stale_threshold_ms,
            min_sources=self.min_sources,
        )
        self._running = True
        self._memory_store = _StubMemoryStore()
        self._setup_signals()

    def _setup_signals(self) -> None:
        try:
            signal.signal(signal.SIGTERM, self._handle_shutdown)
            signal.signal(signal.SIGINT, self._handle_shutdown)
        except (ValueError, OSError):
            logger.warning("signal_setup_skipped", extra={"reason": "restricted environment"})

    def _handle_shutdown(self, signum: int, frame: Any) -> None:
        logger.info("shutdown_signal_received", extra={"signum": signum})
        self._running = False

    def process_signal(self, raw_json: str, trace_id: str) -> list[AnomalyAlert]:
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error("invalid_json", extra={"trace_id": trace_id, "error": str(e)})
            raise AppError(
                "VAL_INVALID_JSON", "Failed to parse request JSON", retryable=False
            ) from e

        if not isinstance(payload, dict):
            raise AppError(
                "VAL_INVALID_PAYLOAD", "Request payload must be an object", retryable=False
            )

        try:
            sig = SpreadSignal(**payload)
        except Exception as e:
            logger.error("model_validation_failed", extra={"trace_id": trace_id, "error": str(e)})
            raise AppError(
                "VAL_MODEL_ERROR", "SpreadSignal validation failed", retryable=False
            ) from e

        if not sig.source_uri:
            raise AppError(
                "VAL_MISSING_SOURCE", "source_uri is mandatory per ADR-006", retryable=False
            )

        alerts: list[AnomalyAlert] = []
        now_ns = int(time.time() * 1e9)

        if self.detector.detect_stale_data(sig.timestamp_ns, now_ns):
            alerts.append(
                AnomalyAlert(
                    severity="warning",
                    symbol=sig.symbol,
                    exchange=sig.buy_exchange,
                    issue="stale_data",
                    details="Market data timestamp exceeds stale threshold",
                    trace_id=trace_id,
                    timestamp_ms=int(time.time() * 1000),
                )
            )

        spread_alert = self.detector.detect_spread_anomaly(sig, trace_id)
        if spread_alert is not None:
            alerts.append(spread_alert)

        self._memory_store.append({
            "trace_id": trace_id,
            "alerts_count": len(alerts),
            "symbol": sig.symbol,
            "agent_id": "data_quality_agent",
            "source_uri": sig.source_uri,
        })

        for alert in alerts:
            logger.warning(
                "anomaly_detected",
                extra={"trace_id": trace_id, "alert": alert.model_dump()},
            )

        return alerts

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "liveness": self._running,
            "readiness": True,
            "timestamp_ms": int(time.time() * 1000),
        }
