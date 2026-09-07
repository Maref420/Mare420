# MODULE: atlas-memory-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: Python client for Rust MemoryGraph with circuit-breaker + cache.
# WARNING: No bare except. All errors mapped to MemoryStoreError.
# POLICY: source_uri + agent_id mandatory per ADR-006.
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class MemoryStoreError(Exception):
    def __init__(self, code: str, message: str, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


class CachedEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    data: dict[str, Any]
    cached_at_ns: int
    ttl_ns: int

    def is_expired(self, now_ns: int) -> bool:
        if self.ttl_ns == 0:
            return False
        return (now_ns - self.cached_at_ns) > self.ttl_ns


class GovernedMemoryStore:
    def __init__(
        self,
        agent_id: str,
        source_uri: str,
        cache_ttl_ns: int = 30_000_000_000,
        max_cache_size: int = 1000,
        failure_threshold: int = 5,
        recovery_timeout_secs: float = 30.0,
    ) -> None:
        if not agent_id:
            raise MemoryStoreError(
                "VAL_MISSING_AGENT_ID", "agent_id mandatory per ADR-006", False
            )
        if not source_uri:
            raise MemoryStoreError(
                "VAL_MISSING_SOURCE_BADGE", "source_uri mandatory per ADR-006", False
            )

        self._agent_id = agent_id
        self._source_uri = source_uri
        self._cache_ttl_ns = cache_ttl_ns
        self._max_cache_size = max_cache_size
        self._failure_threshold = failure_threshold
        self._recovery_timeout_secs = recovery_timeout_secs

        self._cache: dict[str, CachedEntry] = {}
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._read_count = 0
        self._write_count = 0
        self._cache_hits = 0
        self._exception_count = 0

    @property
    def circuit_state(self) -> CircuitState:
        return self._circuit_state

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "reads": self._read_count,
            "writes": self._write_count,
            "cache_hits": self._cache_hits,
            "exceptions": self._exception_count,
            "circuit_state": self._circuit_state.value,
            "cache_size": len(self._cache),
        }

    def _now_ns(self) -> int:
        return int(time.time() * 1e9)

    def _check_circuit(self) -> None:
        if self._circuit_state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self._recovery_timeout_secs:
                self._circuit_state = CircuitState.HALF_OPEN
            else:
                self._exception_count += 1
                raise MemoryStoreError(
                    "DEP_STORE_UNAVAILABLE",
                    "circuit breaker open, Rust store unavailable",
                    True,
                )

    def _record_success(self) -> None:
        self._failure_count = 0
        self._circuit_state = CircuitState.CLOSED

    def _record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        self._exception_count += 1
        if self._failure_count >= self._failure_threshold:
            self._circuit_state = CircuitState.OPEN

    def write_node(
        self,
        node_id: str,
        entity_type: str,
        attributes: dict[str, str],
        ttl_ns: int = 0,
        override_source_uri: Optional[str] = None,
        override_agent_id: Optional[str] = None,
    ) -> dict[str, Any]:
        self._check_circuit()

        # Use override if explicitly provided (even if empty string), else default
        src = override_source_uri if override_source_uri is not None else self._source_uri
        aid = override_agent_id if override_agent_id is not None else self._agent_id

        if not src:
            self._record_failure()
            raise MemoryStoreError(
                "VAL_MISSING_SOURCE_BADGE", "source_uri mandatory per ADR-006", False
            )
        if not aid:
            self._record_failure()
            raise MemoryStoreError(
                "VAL_MISSING_AGENT_ID", "agent_id mandatory per ADR-006", False
            )
        if not node_id:
            self._record_failure()
            raise MemoryStoreError(
                "VAL_INVALID_NODE_ID", "node_id cannot be empty", False
            )

        now = self._now_ns()
        node_data = {
            "node_id": node_id,
            "entity_type": entity_type,
            "attributes": attributes,
            "source_uri": src,
            "agent_id": aid,
            "ttl_ns": ttl_ns,
            "created_at_ns": now,
            "updated_at_ns": now,
        }

        try:
            self._validate_node(node_data)
            self._cache[node_id] = CachedEntry(
                data=node_data, cached_at_ns=now, ttl_ns=ttl_ns
            )
            self._evict_cache_if_needed()
            self._write_count += 1
            self._record_success()
            return node_data
        except MemoryStoreError:
            self._record_failure()
            raise
        except Exception as e:
            self._record_failure()
            raise MemoryStoreError(
                "INT_INVARIANT_BROKEN", f"unexpected error: {e}", False
            ) from e

    def read_node(self, node_id: str) -> Optional[dict[str, Any]]:
        self._check_circuit()
        self._read_count += 1
        now = self._now_ns()

        cached = self._cache.get(node_id)
        if cached is not None:
            if not cached.is_expired(now):
                self._cache_hits += 1
                self._record_success()
                return cached.data
            else:
                del self._cache[node_id]
                self._exception_count += 1
                raise MemoryStoreError(
                    "VAL_TTL_EXPIRED", f"node {node_id} exceeded TTL", False
                )

        self._record_success()
        return None

    def search(self, keyword: str) -> list[dict[str, Any]]:
        self._check_circuit()
        kw = keyword.lower()
        now = self._now_ns()
        results: list[dict[str, Any]] = []

        for entry in self._cache.values():
            if entry.is_expired(now):
                continue
            data = entry.data
            if (
                kw in data.get("entity_type", "").lower()
                or kw in data.get("node_id", "").lower()
                or any(kw in v.lower() for v in data.get("attributes", {}).values())
            ):
                results.append(data)

        self._record_success()
        return results

    def _validate_node(self, node: dict[str, Any]) -> None:
        if not node.get("source_uri"):
            raise MemoryStoreError(
                "VAL_MISSING_SOURCE_BADGE", "source_uri mandatory", False
            )
        if not node.get("agent_id"):
            raise MemoryStoreError(
                "VAL_MISSING_AGENT_ID", "agent_id mandatory", False
            )
        if not node.get("node_id"):
            raise MemoryStoreError(
                "VAL_INVALID_NODE_ID", "node_id cannot be empty", False
            )

    def _evict_cache_if_needed(self) -> None:
        if len(self._cache) <= self._max_cache_size:
            return
        now = self._now_ns()
        expired_keys = [k for k, v in self._cache.items() if v.is_expired(now)]
        for k in expired_keys:
            del self._cache[k]
        if len(self._cache) > self._max_cache_size:
            sorted_keys = sorted(
                self._cache.keys(),
                key=lambda k: self._cache[k].cached_at_ns,
            )
            excess = len(self._cache) - self._max_cache_size
            for k in sorted_keys[:excess]:
                del self._cache[k]
