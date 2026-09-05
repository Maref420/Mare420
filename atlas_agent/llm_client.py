"""LLM Client with 0G AI Router + Resource Protection + Cache."""

__all__ = ["LLMClient", "ResourceConfig", "CircuitBreaker", "ProviderStatus"]

import json
import os
import random
import time
import logging
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from dotenv import load_dotenv
from .llm_cache import LLMCache
from .restriction_guard import RestrictionGuard

load_dotenv()
logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class ResourceConfig:
    max_concurrent_requests: int = 2
    request_timeout_seconds: int = 60
    max_response_tokens: int = 8192
    rate_limit_rpm: int = 20
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_seconds: int = 60


@dataclass
class CircuitBreaker:
    failure_count: int = 0
    last_failure_time: float = 0.0
    status: ProviderStatus = ProviderStatus.HEALTHY
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record_success(self) -> None:
        with self.lock:
            self.failure_count = 0
            self.status = ProviderStatus.HEALTHY

    def record_failure(self, config: ResourceConfig) -> None:
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= config.circuit_breaker_threshold:
                self.status = ProviderStatus.CIRCUIT_OPEN
                logger.warning("Circuit breaker OPEN after %d failures", self.failure_count)

    def allow_request(self, config: ResourceConfig) -> bool:
        with self.lock:
            if self.status != ProviderStatus.CIRCUIT_OPEN:
                return True
            elapsed = time.time() - self.last_failure_time
            if elapsed >= config.circuit_breaker_reset_seconds:
                self.status = ProviderStatus.DEGRADED
                self.failure_count = 0
                logger.info("Circuit breaker reset to DEGRADED")
                return True
            return False


class LLMClient:
    """Production-grade LLM client using 0G AI Router only."""

    def __init__(self, config: Optional[ResourceConfig] = None) -> None:
        self.config = config or ResourceConfig()
        self._circuit_breaker = CircuitBreaker()
        self._request_semaphore = threading.Semaphore(self.config.max_concurrent_requests)
        self._request_timestamps: list[float] = []
        self._rate_lock = threading.Lock()
        self._cache = LLMCache()
        self._guard = RestrictionGuard()

        self._og_api_key = os.getenv("OG_API_KEY", "")
        self._og_base_url = os.getenv("OG_BASE_URL", "https://router-api.0g.ai/v1/messages")
        self.model = os.getenv("OG_MODEL", "0GM-1.0-35B-A3B")
        self.fallback_model = os.getenv("LLM_FALLBACK_MODEL", self.model)

        if not self._og_api_key:
            raise ValueError("OG_API_KEY missing in .env")

        logger.info("LLMClient: provider=og model=%s fallback=%s", self.model, self.fallback_model)

    def __repr__(self) -> str:
        return f"LLMClient(model={self.model}, key=***HIDDEN***)"

    def __str__(self) -> str:
        return self.__repr__()

    def _check_rate_limit(self) -> None:
        now = time.time()
        with self._rate_lock:
            self._request_timestamps = [t for t in self._request_timestamps if now - t < 60.0]
            if len(self._request_timestamps) >= self.config.rate_limit_rpm:
                raise RuntimeError(f"Rate limit exceeded: {self.config.rate_limit_rpm} RPM")
            self._request_timestamps.append(now)

    def _check_restricted_content(self, requirement: str) -> Optional[str]:
        decision = self._guard.check_request(requirement)
        if not decision.allowed:
            return decision.category.value if decision.category else "restricted"
        return None

    def _call_api(self, prompt: str, model: str, temperature: float) -> str:
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                payload = json.dumps({
                    "model": model,
                    "max_tokens": self.config.max_response_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                }).encode()

                req = urllib.request.Request(
                    self._og_base_url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": self._og_api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=self.config.request_timeout_seconds) as resp:
                    body = json.loads(resp.read().decode())

                text_parts = []
                for block in body.get("content", []):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "thinking":
                        logger.debug("OG thinking skipped (%d chars)", len(block.get("thinking", "")))

                content = "\n".join(text_parts)
                if not content or len(content.strip()) == 0:
                    raise RuntimeError(f"OG model {model} returned empty content")
                return content

            except urllib.error.HTTPError as e:
                err_body = ""
                try:
                    raw = e.read().decode()[:300]
                    # Never expose API key in error messages
                    if self._og_api_key and len(self._og_api_key) > 8:
                        raw = raw.replace(self._og_api_key, "***REDACTED***")
                    err_body = raw
                except Exception:
                    pass

                if e.code == 429 and attempt < max_attempts - 1:
                    wait = min(2 ** attempt + random.uniform(0, 1), 30)
                    logger.warning("OG rate limited (attempt %d/%d), waiting %.1fs", attempt + 1, max_attempts, wait)
                    time.sleep(wait)
                elif e.code in (502, 503, 504) and attempt < max_attempts - 1:
                    wait = min(2 ** attempt + random.uniform(0, 1), 15)
                    logger.warning("OG server error %d (attempt %d/%d), waiting %.1fs", e.code, attempt + 1, max_attempts, wait)
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"OG API HTTP {e.code}: {err_body}") from e

            except urllib.error.URLError as e:
                if attempt < max_attempts - 1:
                    wait = min(2 ** attempt + random.uniform(0, 1), 15)
                    logger.warning("OG connection error (attempt %d/%d), waiting %.1fs", attempt + 1, max_attempts, wait)
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"OG connection failed: {e}") from e

            except (json.JSONDecodeError, KeyError, IndexError) as e:
                raise RuntimeError(f"OG response parse error: {e}") from e

        raise RuntimeError(f"OG API failed after {max_attempts} attempts")

    def generate_code(self, requirement: str, language: str) -> str:
        restricted = self._check_restricted_content(requirement)
        if restricted:
            raise ValueError(
                f"Rejected: restricted category '{restricted}'. "
                f"CONSTITUTION.md section 17 prohibits external AI for: "
                f"HFT core, execution logic, risk systems, trading strategies."
            )

        if not self._circuit_breaker.allow_request(self.config):
            raise RuntimeError("Circuit breaker OPEN - API temporarily unavailable")

        self._check_rate_limit()

        try:
            from .governance_prompt_builder import build_governance_prompt
            prompt, prompt_hash = build_governance_prompt(
                requirement=requirement,
                language=language,
                module_name="generated_module",
                project_name="Atlas AI",
                architecture="Gateway(Go) -> Agent(Python) -> Engine(Rust)",
                modules=[{"name": "generated_module"}],
            )
            logger.info("GovernancePromptBuilder hash=%s", prompt_hash)
        except ImportError:
            prompt = (
                f"You are a senior software engineer.\n"
                f"Generate professional, secure {language} code for:\n"
                f"{requirement}\n"
                f"Include error handling. Production-ready only."
            )

        cached = self._cache.get(prompt, self.model, 0.2)
        if cached is not None:
            logger.info("Cache HIT - skipping API call")
            return cached

        acquired = self._request_semaphore.acquire(timeout=self.config.request_timeout_seconds)
        if not acquired:
            raise RuntimeError("Max concurrent requests reached")

        try:
            try:
                content = self._call_api(prompt, self.model, 0.2)
            except RuntimeError as primary_err:
                if self.fallback_model != self.model:
                    logger.warning(
                        "Primary %s failed (%s), trying fallback %s",
                        self.model,
                        type(primary_err).__name__,
                        self.fallback_model,
                    )
                    try:
                        content = self._call_api(prompt, self.fallback_model, 0.2)
                    except RuntimeError as fallback_err:
                        self._circuit_breaker.record_failure(self.config)
                        raise RuntimeError(
                            f"Both models failed. Primary: {primary_err}. Fallback: {fallback_err}"
                        ) from fallback_err
                else:
                    self._circuit_breaker.record_failure(self.config)
                    raise

            self._cache.put(prompt, self.model, 0.2, content)
            self._circuit_breaker.record_success()
            return content

        finally:
            self._request_semaphore.release()

    def analyze_security(self, code: str) -> str:
        if not self._circuit_breaker.allow_request(self.config):
            raise RuntimeError("Circuit breaker OPEN")

        self._check_rate_limit()

        prompt = (
            f"Review for security vulnerabilities "
            f"(SQL Injection, XSS, Hardcoded Secrets):\n{code}"
        )

        cached = self._cache.get(prompt, self.model, 0.1)
        if cached is not None:
            return cached

        acquired = self._request_semaphore.acquire(timeout=self.config.request_timeout_seconds)
        if not acquired:
            raise RuntimeError("Max concurrent requests reached")

        try:
            content = self._call_api(prompt, self.model, 0.1)
            self._cache.put(prompt, self.model, 0.1, content)
            self._circuit_breaker.record_success()
            return content
        except RuntimeError as e:
            self._circuit_breaker.record_failure(self.config)
            raise RuntimeError(f"Security analysis failed: {e}") from e
        finally:
            self._request_semaphore.release()
