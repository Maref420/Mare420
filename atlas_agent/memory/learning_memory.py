"""Internal Learning Memory — Generator-scoped experience store.

ONE file: portable_memory.jsonl (append-only, <50MB)
Module-scoped: ONLY code generation experiences.
NOT trading agent memory (intelligence/memory_system/).
Portable: copy file = AI remembers everything.
RAM: <20MB | HDD: <50MB | CPU: negligible
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from .experience import Experience, Decision, Source, Method, Artifact, Outcome

logger = logging.getLogger(__name__)

MEMORY_FILE = Path(__file__).parent / "portable_memory.jsonl"
MAX_ENTRIES = 10000
MAX_SIZE_MB = 50


class LearningMemory:
    """Append-only experience store with anti-pattern learning."""

    def __init__(self, memory_path: Path = MEMORY_FILE):
        self.path = memory_path
        self._index: dict[str, Experience] = {}
        self._anti_patterns: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            logger.info("No existing memory - starting fresh")
            return
        size_mb = self.path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_SIZE_MB:
            self._prune()
        with open(self.path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    exp = Experience.from_jsonl(line)
                    self._index[exp.id] = exp
                    self._anti_patterns.update(exp.anti_patterns)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Corrupt entry skipped: %s", e)
        logger.info("Loaded: %d experiences, %d anti-patterns",
                    len(self._index), len(self._anti_patterns))

    @property
    def experiences(self) -> list:
        """Public read-only access to all experiences (memory contract compliant)."""
        return list(self._index.values())

    @property
    def anti_patterns(self) -> set:
        """Public read-only access to anti-patterns (memory contract compliant)."""
        return set(self._anti_patterns)

    def _prune(self) -> None:
        if not self.path.exists():
            return
        lines = self.path.read_text().strip().split("\n")
        if len(lines) <= MAX_ENTRIES:
            return
        kept = lines[-MAX_ENTRIES:]
        self.path.write_text("\n".join(kept) + "\n")
        logger.info("Pruned: %d -> %d entries", len(lines), MAX_ENTRIES)

    def record(self, source: Source, method: Method, artifact: Artifact,
               decision: Decision, reason: str, quality_score: float,
               anti_patterns: Optional[list[str]] = None) -> Experience:
        exp = Experience(
            id=Experience.generate_id(),
            ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            type="generation",
            source=source, method=method, artifact=artifact,
            outcome=Outcome(human_decision=decision.value,
                           reason=reason, quality_score=quality_score),
            anti_patterns=anti_patterns or [],
            tags=[artifact.language, artifact.module],
        )
        if decision == Decision.REJECTED and anti_patterns:
            self._anti_patterns.update(anti_patterns)
            exp.tags.append("REJECTED")
        with open(self.path, "a") as f:
            f.write(exp.to_jsonl() + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._index[exp.id] = exp
        return exp

    def get_positive(self, language: str, module: str, limit: int = 3) -> list[Experience]:
        candidates = [e for e in self._index.values()
                      if e.outcome.human_decision == "approved"
                      and e.artifact.language == language
                      and module in e.artifact.module]
        candidates.sort(key=lambda e: e.outcome.quality_score, reverse=True)
        return candidates[:limit]

    def get_negative(self, language: str, limit: int = 2) -> list[Experience]:
        return [e for e in self._index.values()
                if e.outcome.human_decision == "rejected"
                and e.artifact.language == language][:limit]

    def get_anti_patterns(self) -> set[str]:
        return self._anti_patterns.copy()

    def stats(self) -> dict:
        approved = sum(1 for e in self._index.values() if e.outcome.human_decision == "approved")
        rejected = sum(1 for e in self._index.values() if e.outcome.human_decision == "rejected")
        return {
            "total": len(self._index),
            "approved": approved,
            "rejected": rejected,
            "anti_patterns": len(self._anti_patterns),
            "file_kb": self.path.stat().st_size // 1024 if self.path.exists() else 0,
        }
