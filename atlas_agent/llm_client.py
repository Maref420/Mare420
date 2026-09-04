"""LLM Client with Resource Protection + Cache + Multi-Model Fallback.

Governed by: contracts/schemas/ai/llm-invocation-v1.json
CONSTITUTION.md §17 enforced client-side.

Resource budget (6GB RAM / 6 CPU VPS):
- RAM: <20MB | CPU: I/O bound | HDD: <1MB (cache file)
"""

import os
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from dotenv import load_dotenv
from groq import Groq, APIError, APIConnectionError, APITimeoutError, RateLimitError
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
    """Hard limits to protect 6GB RAM / 6 CPU VPS."""
    max_concurrent_requests: int = 2
    request_timeout_seconds: int = 30
    max_response_tokens: int = 4096
    rate_limit_rpm: int = 20
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_seconds: int = 60


@dataclass
class CircuitBreaker:
    """Prevents cascading failures when API is down."""
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
    """Production-grade LLM client with cache, fallback, and resource protection."""

    RESTRICTED_CATEGORIES = {
        "hft_core": ["high-frequency", "hft core", "millisecond execution", "nanosecond timing"],
        "execution_logic": ["order execution", "trade execution", "execution engine", "exchange order"],
        "risk_systems": ["risk engine", "risk management", "position limits", "exposure control"],
        "trading_strategies": ["trading strategy", "strategy logic", "signal generation", "backtest"],
    }

    def __init__(self, config: Optional[ResourceConfig] = None) -> None:
        self.config = config or ResourceConfig()
        self._circuit_breaker = CircuitBreaker()
        self._request_semaphore = threading.Semaphore(self.config.max_concurrent_requests)
        self._request_timestamps: list[float] = []
        self._rate_lock = threading.Lock()
        self._cache = LLMCache()
        self._guard = RestrictionGuard()

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY missing in .env")

        self.client = Groq(
            api_key=api_key,
            timeout=self.config.request_timeout_seconds,
            max_retries=4,
        )
        self.model = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
        self.fallback_model = os.getenv("LLM_FALLBACK_MODEL", "openai/gpt-oss-20b")
        logger.info("LLMClient: model=%s fallback=%s", self.model, self.fallback_model)

    def _check_rate_limit(self) -> None:
        now = time.time()
        with self._rate_lock:
            self._request_timestamps = [t for t in self._request_timestamps if now - t < 60.0]
            if len(self._request_timestamps) >= self.config.rate_limit_rpm:
                raise RuntimeError(f"Rate limit exceeded: {self.config.rate_limit_rpm} RPM")
            self._request_timestamps.append(now)

    def _check_restricted_content(self, requirement: str) -> Optional[str]:
        """Delegate to 3-layer RestrictionGuard (§17 enforcement)."""
        decision = self._guard.check_request(requirement)
        if not decision.allowed:
            return decision.category.value if decision.category else "restricted"
        return None


    def _call_api(self, prompt: str, model: str, temperature: float) -> str:
        """Single API call with exponential backoff on 429."""
        import random
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=self.config.max_response_tokens,
                )
                content = response.choices[0].message.content
                if content is None or len(content.strip()) == 0:
                    raise RuntimeError(f"Model {model} returned empty content")
                return content
            except RateLimitError as e:
                if attempt < max_attempts - 1:
                    wait = min(2 ** attempt + random.uniform(0, 1), 30)
                    logger.warning("Rate limited on %s (attempt %d/%d), waiting %.1fs",
                                  model, attempt + 1, max_attempts, wait)
                    time.sleep(wait)
                else:
                    raise
            except (APITimeoutError, APIConnectionError) as e:
                if attempt < max_attempts - 1:
                    wait = min(2 ** attempt + random.uniform(0, 1), 15)
                    logger.warning("API error on %s (attempt %d/%d), waiting %.1fs: %s",
                                  model, attempt + 1, max_attempts, wait, e)
                    time.sleep(wait)
                else:
                    raise

    def generate_code(self, requirement: str, language: str) -> str:
        """Generate code with cache, fallback, and full resource protection."""
        restricted = self._check_restricted_content(requirement)
        if restricted:
            raise ValueError(
                f"Rejected: restricted category '{restricted}'. "
                f"CONSTITUTION.md §17 prohibits external AI for: "
                f"HFT core, execution logic, risk systems, trading strategies."
            )

        if not self._circuit_breaker.allow_request(self.config):
            raise RuntimeError("Circuit breaker OPEN — API temporarily unavailable")

        self._check_rate_limit()

        prompt = (
            f"You are a senior software engineer.\n"
            f"Generate professional, secure {language} code for:\n"
            f"{requirement}\n"
            f"Include error handling. Production-ready only."
        )

        # Step 1: Check cache
        cached = self._cache.get(prompt, self.model, 0.2)
        if cached is not None:
            logger.info("Cache HIT — skipping API call")
            return cached

        # Step 2: Acquire semaphore
        acquired = self._request_semaphore.acquire(timeout=self.config.request_timeout_seconds)
        if not acquired:
            raise RuntimeError("Max concurrent requests reached")

        try:
            # Step 3: Try primary model
            try:
                content = self._call_api(prompt, self.model, 0.2)
            except (RuntimeError, RateLimitError, APITimeoutError, APIConnectionError, APIError) as primary_err:
                # Step 4: Try fallback model
                logger.warning("Primary model %s failed (%s), trying fallback %s",
                              self.model, type(primary_err).__name__, self.fallback_model)
                try:
                    content = self._call_api(prompt, self.fallback_model, 0.2)
                except (RuntimeError, RateLimitError, APITimeoutError, APIConnectionError, APIError) as fallback_err:
                    self._circuit_breaker.record_failure(self.config)
                    raise RuntimeError(
                        f"Both models failed. Primary: {primary_err}. Fallback: {fallback_err}"
                    ) from fallback_err

            # Step 5: Store in cache
            self._cache.put(prompt, self.model, 0.2, content)
            self._circuit_breaker.record_success()
            return content

        finally:
            self._request_semaphore.release()

    def analyze_security(self, code: str) -> str:
        """Security analysis with cache and resource protection."""
        if not self._circuit_breaker.allow_request(self.config):
            raise RuntimeError("Circuit breaker OPEN")

        self._check_rate_limit()

        prompt = (
            f"Review for security vulnerabilities "
            f"(SQL Injection, XSS, Hardcoded Secrets):\n{code}"
        )

        # Check cache
        cached = self._cache.get(prompt, self.model, 0.1)
        if cached is not None:
            return cached

        acquired = self._request_semaphore.acquire(timeout=self.config.request_timeout_seconds)
        if not acquired:
            raise RuntimeError("Max concurrent requests reached")

        try:
            try:
                content = self._call_api(prompt, self.model, 0.1)
            except (RuntimeError, RateLimitError, APITimeoutError, APIConnectionError, APIError):
                content = self._call_api(prompt, self.fallback_model, 0.1)

            self._cache.put(prompt, self.model, 0.1, content)
            self._circuit_breaker.record_success()
            return content
        except (RateLimitError, APITimeoutError, APIConnectionError, APIError, RuntimeError) as e:
            self._circuit_breaker.record_failure(self.config)
            raise RuntimeError(f"Security analysis failed: {e}") from e
        finally:
            self._request_semaphore.release()
