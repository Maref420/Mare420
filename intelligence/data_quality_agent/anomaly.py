# MODULE: atlas-data-quality-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# WARNING: No bare except. Explicit error handling only.
from __future__ import annotations

import logging
import time
from typing import Literal

from .models import AnomalyAlert, SpreadSignal, ValidationReport

logger = logging.getLogger(__name__)


class AnomalyDetector:
    def __init__(
        self,
        spread_threshold_bps: int = 50,
        stale_threshold_ms: int = 5000,
        min_sources: int = 2,
    ) -> None:
        self.spread_threshold_bps = spread_threshold_bps
        self.stale_threshold_ms = stale_threshold_ms
        self.min_sources = min_sources

    def detect_spread_anomaly(
        self, signal: SpreadSignal, trace_id: str
    ) -> AnomalyAlert | None:
        if signal.spread_bps <= self.spread_threshold_bps:
            return None
        severity: Literal["warning", "critical"] = (
            "critical" if signal.spread_bps > 200 else "warning"
        )
        ts_ms = int(time.time() * 1000)
        return AnomalyAlert(
            severity=severity,
            symbol=signal.symbol,
            exchange=f"{signal.buy_exchange}/{signal.sell_exchange}",
            issue="spread_anomaly",
            details=(
                f"Spread {signal.spread_bps}bps exceeds "
                f"threshold {self.spread_threshold_bps}bps"
            ),
            trace_id=trace_id,
            timestamp_ms=ts_ms,
        )

    def detect_stale_data(self, timestamp_ns: int, now_ns: int) -> bool:
        diff_ms = (now_ns - timestamp_ns) // 1_000_000
        return diff_ms > self.stale_threshold_ms

    def detect_missing_sources(self, source_count: int) -> bool:
        return source_count < self.min_sources

    def evaluate(
        self, report: ValidationReport, trace_id: str
    ) -> list[AnomalyAlert]:
        alerts: list[AnomalyAlert] = []
        ts_ms = int(time.time() * 1000)

        if not report.is_valid:
            alerts.append(
                AnomalyAlert(
                    severity="critical",
                    symbol=report.symbol,
                    exchange="system",
                    issue="validation_failure",
                    details="Report failed validation checks",
                    trace_id=trace_id,
                    timestamp_ms=ts_ms,
                )
            )

        if self.detect_missing_sources(report.source_count):
            alerts.append(
                AnomalyAlert(
                    severity="warning",
                    symbol=report.symbol,
                    exchange="data_source",
                    issue="missing_sources",
                    details=(
                        f"Source count {report.source_count} "
                        f"below minimum {self.min_sources}"
                    ),
                    trace_id=trace_id,
                    timestamp_ms=ts_ms,
                )
            )

        if report.spread_bps > self.spread_threshold_bps:
            sev: Literal["warning", "critical"] = (
                "critical" if report.spread_bps > 200 else "warning"
            )
            alerts.append(
                AnomalyAlert(
                    severity=sev,
                    symbol=report.symbol,
                    exchange="aggregator",
                    issue="high_spread",
                    details=f"Median spread {report.spread_bps}bps exceeds threshold",
                    trace_id=trace_id,
                    timestamp_ms=ts_ms,
                )
            )

        for exc in report.anomalous_exchanges:
            alerts.append(
                AnomalyAlert(
                    severity="warning",
                    symbol=report.symbol,
                    exchange=exc,
                    issue="anomalous_exchange",
                    details=f"Exchange {exc} flagged as anomalous by cross-validator",
                    trace_id=trace_id,
                    timestamp_ms=ts_ms,
                )
            )

        return alerts
