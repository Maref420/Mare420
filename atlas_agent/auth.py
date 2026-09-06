"""Atlas AI Agent Authentication & Rate Limiting Middleware.

Governance Reference: CONSTITUTION.md v1.2, Section 17
Module: atlas_agent/auth.py
Owner: intelligence (Python)
Description: API key validation with constant-time comparison and
             sliding-window rate limiting. Stdlib-only.
"""
from __future__ import annotations

import hmac
import logging
import os
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """Thread-safe authentication and rate-limiting middleware.

    - API keys from AGENT_API_KEYS env var (comma-separated)
    - If unset → dev mode (auth disabled, warning logged)
    - Constant-time key comparison via hmac.compare_digest
    - Sliding window rate limiter per key
    - Bypass for /health/* and /metrics paths
    """

    _instance: AuthMiddleware | None = None
    _init_lock = threading.Lock()

    def __new__(cls) -> AuthMiddleware:
        """Singleton pattern — one middleware instance per process."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._rps: int = int(os.environ.get("AGENT_RATE_LIMIT_RPS", "10"))
        self._burst: int = int(os.environ.get("AGENT_RATE_LIMIT_BURST", "20"))
        self._lock = threading.Lock()
        self._windows: dict[bytes, deque[float]] = {}
        self._keys: set[bytes] = set()
        self._dev_mode: bool = False
        self._setup_keys()
        self._initialized = True
        if self._dev_mode:
            logger.warning(
                "auth_dev_mode_enabled",
                extra={"rps": self._rps, "burst": self._burst},
            )

    @classmethod
    def reset(cls) -> None:
        """Reset singleton — for testing only."""
        with cls._init_lock:
            cls._instance = None

    def _setup_keys(self) -> None:
        raw = os.environ.get("AGENT_API_KEYS", "").strip()
        if not raw:
            self._dev_mode = True
            return
        for part in raw.split(","):
            cleaned = part.strip()
            if cleaned:
                self._keys.add(cleaned.encode("utf-8"))
        logger.info("auth_keys_loaded", extra={"count": len(self._keys)})

    def _check_rate_limit(self, key: bytes) -> bool:
        with self._lock:
            now = time.monotonic()
            if key not in self._windows:
                self._windows[key] = deque(maxlen=self._burst * 2)
            window = self._windows[key]
            while window and window[0] <= now - 1.0:
                window.popleft()
            if len(window) >= self._burst:
                return False
            window.append(now)
            return True

    def check(
        self,
        headers: dict[str, str],
        path: str,
        trace_id: str,
    ) -> tuple[bool, dict[str, Any] | None]:
        """Validate authentication and rate limits.

        Returns:
            (True, None) if authorized.
            (False, error_dict) if denied.
        """
        if self._dev_mode:
            return True, None

        # Bypass health and metrics
        if path.startswith("/health") or path.startswith("/metrics"):
            return True, None

        # Extract key (case-insensitive header lookup)
        raw_key = None
        for k, v in headers.items():
            if k.lower() == "x-api-key":
                raw_key = v
                break
        if not raw_key:
            logger.warning("auth_missing_key", extra={"trace_id": trace_id})
            return False, {
                "trace_id": trace_id,
                "service": "agent",
                "code": "AUTH_MISSING_KEY",
                "retryable": False,
                "http_status": 401,
                "message": "Missing X-API-Key header",
                "details": {},
                "cause_chain": [],
                "timestamp_ms": int(time.time() * 1000),
            }

        # Constant-time comparison
        provided = raw_key.encode("utf-8")
        key_valid = any(hmac.compare_digest(provided, stored) for stored in self._keys)

        if not key_valid:
            logger.warning("auth_invalid_key", extra={"trace_id": trace_id})
            return False, {
                "trace_id": trace_id,
                "service": "agent",
                "code": "AUTH_INVALID_KEY",
                "retryable": False,
                "http_status": 401,
                "message": "Invalid API key",
                "details": {},
                "cause_chain": [],
                "timestamp_ms": int(time.time() * 1000),
            }

        # Rate limit
        if not self._check_rate_limit(provided):
            logger.warning("auth_rate_limited", extra={"trace_id": trace_id})
            return False, {
                "trace_id": trace_id,
                "service": "agent",
                "code": "AUTH_RATE_LIMITED",
                "retryable": True,
                "http_status": 429,
                "message": "Rate limit exceeded",
                "details": {"rps": self._rps, "burst": self._burst},
                "cause_chain": [],
                "timestamp_ms": int(time.time() * 1000),
            }

        return True, None
