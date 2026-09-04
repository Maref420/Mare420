"""LLM Response Cache — Eliminate redundant API calls.

Design:
- Hash-based cache key (prompt + model + temperature)
- TTL: 24 hours (code requirements rarely change meaningfully)
- Max size: 100 entries (~5MB max)
- Storage: JSON file on disk (survives restarts)
- Thread-safe for concurrent access

Impact: Repeated requests go from 3s → 0s.
"""

__all__ = ['LLMCache']


import hashlib
import json
import logging
import time
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent / "llm_cache.json"
MAX_ENTRIES = 100
TTL_SECONDS = 86400  # 24 hours


class LLMCache:
    """Thread-safe LLM response cache with TTL and size limits."""

    def __init__(self, cache_path: Path = CACHE_FILE):
        self.path = cache_path
        self._lock = threading.Lock()
        self._cache: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
            # Filter expired entries
            now = time.time()
            self._cache = {
                k: v for k, v in data.items()
                if now - v.get("ts", 0) < TTL_SECONDS
            }
            logger.info("Cache loaded: %d valid entries", len(self._cache))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Cache corrupt, starting fresh: %s", e)
            self._cache = {}

    def _save(self) -> None:
        try:
            with open(self.path, "w") as f:
                json.dump(self._cache, f)
        except OSError as e:
            logger.warning("Cache save failed: %s", e)

    def _make_key(self, prompt: str, model: str, temperature: float) -> str:
        raw = f"{model}:{temperature}:{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def get(self, prompt: str, model: str, temperature: float) -> Optional[str]:
        """Get cached response. Returns None on miss or expiry."""
        key = self._make_key(prompt, model, temperature)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() - entry["ts"] > TTL_SECONDS:
                del self._cache[key]
                return None
            entry["hits"] = entry.get("hits", 0) + 1
            logger.info("Cache HIT: key=%s hits=%d", key[:8], entry["hits"])
            return entry["response"]

    def put(self, prompt: str, model: str, temperature: float, response: str) -> None:
        """Store response in cache."""
        key = self._make_key(prompt, model, temperature)
        with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= MAX_ENTRIES and key not in self._cache:
                oldest_key = min(self._cache, key=lambda k: self._cache[k]["ts"])
                del self._cache[oldest_key]
            self._cache[key] = {
                "response": response,
                "ts": time.time(),
                "model": model,
                "hits": 0,
                "len": len(response),
            }
            self._save()
        logger.info("Cache STORE: key=%s len=%d", key[:8], len(response))

    def stats(self) -> dict:
        with self._lock:
            total_hits = sum(e.get("hits", 0) for e in self._cache.values())
            return {
                "entries": len(self._cache),
                "total_hits_saved": total_hits,
                "estimated_seconds_saved": total_hits * 3,  # ~3s per call
                "file_kb": self.path.stat().st_size // 1024 if self.path.exists() else 0,
            }