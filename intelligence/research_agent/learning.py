# MODULE: atlas-research-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# WARNING: No bare except. Deterministic learning logic only.
from __future__ import annotations

import logging
from typing import Any

from .models import ExperimentResult, ForensicsSignal, PatternRecord

logger = logging.getLogger(__name__)


class LearningPackage:
    def __init__(self) -> None:
        self._patterns: dict[str, PatternRecord] = {}

    def register_pattern(self, record: PatternRecord) -> None:
        self._patterns[record.pattern_id] = record
        logger.info("pattern_registered", extra={
            "pattern_id": record.pattern_id, "symbol": record.symbol,
        })

    def score_signal(self, signal: ForensicsSignal) -> tuple[float, list[str]]:
        base_boost: float = 0.0
        if signal.aqs_score > 70 and signal.vpin_toxicity < 0.3 and not signal.spoofing_detected:
            base_boost = 0.1

        matched_ids: list[str] = []
        for pattern in self._patterns.values():
            if pattern.symbol != signal.symbol:
                continue
            if not self._conditions_match(pattern.conditions, signal):
                continue
            if pattern.win_rate > 0.6:
                base_boost += 0.05 * pattern.win_rate
                matched_ids.append(pattern.pattern_id)

        total_boost = min(base_boost, 0.3)
        return round(total_boost, 4), matched_ids

    @staticmethod
    def _conditions_match(conditions: dict[str, Any], signal: ForensicsSignal) -> bool:
        for key, value in conditions.items():
            if key == "min_aqs" and signal.aqs_score < value:
                return False
            if key == "max_toxicity" and signal.vpin_toxicity > value:
                return False
            if key == "no_spoofing" and signal.spoofing_detected == value:
                return False
            if key == "min_imbalance" and abs(signal.orderbook_imbalance) < value:
                return False
        return True

    def record_experiment(self, result: ExperimentResult) -> None:
        pattern = self._patterns.get(result.pattern_id)
        if pattern is None:
            logger.warning("pattern_not_found", extra={
                "pattern_id": result.pattern_id,
                "experiment_id": result.experiment_id,
            })
            return

        old_rate = pattern.win_rate
        old_count = pattern.sample_count
        win_val = 1.0 if result.outcome == "win" else 0.0
        new_rate = ((old_rate * old_count) + win_val) / (old_count + 1)

        updated = PatternRecord(
            pattern_id=pattern.pattern_id,
            symbol=pattern.symbol,
            conditions=pattern.conditions,
            win_rate=round(new_rate, 6),
            sample_count=old_count + 1,
            last_seen_ms=result.timestamp_ms,
            source_uri=pattern.source_uri,
        )
        self._patterns[pattern.pattern_id] = updated
        logger.info("experiment_recorded", extra={
            "pattern_id": result.pattern_id,
            "new_win_rate": updated.win_rate,
            "new_count": updated.sample_count,
        })

    def get_top_patterns(self, limit: int = 5) -> list[PatternRecord]:
        return sorted(
            self._patterns.values(),
            key=lambda p: (p.win_rate, p.sample_count),
            reverse=True,
        )[:limit]
