"""Production-grade ErrorEnvelope for Atlas AI Python services.

Governance compliance (Section 6 — Distributed Error Contract):
- All cross-service failures use ErrorEnvelope
- Code families: VAL_, AUTH_, BIZ_, DEP_, RES_, NET_, INT_
- retryable defaults per family
- No secrets, no stack traces in message
- Consumers key off code + retryable only
"""
from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

_HTTP_STATUS_MAP: Dict[str, int] = {
    "VAL_": 400,
    "AUTH_": 401,
    "BIZ_": 422,
    "DEP_": 503,
    "RES_": 429,
    "NET_": 504,
    "INT_": 500,
}

_RETRYABLE_DEFAULTS: Dict[str, bool] = {
    "VAL_": False,
    "AUTH_": False,
    "BIZ_": False,
    "DEP_": True,
    "RES_": True,
    "NET_": True,
    "INT_": False,
}

_VALID_SERVICES = frozenset({"gateway", "agent", "engine"})


def _resolve_code_prefix(code: str) -> str:
    """Extract the family prefix from a full error code."""
    for prefix in _HTTP_STATUS_MAP:
        if code.startswith(prefix):
            return prefix
    return "INT_"


class ErrorEnvelope(BaseModel):
    """Immutable error envelope for cross-service communication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    service: str
    code: str
    retryable: bool
    http_status: int
    message: str
    details: Optional[Dict[str, str]] = None
    cause_chain: Optional[List[Dict[str, str]]] = None
    timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))

    def to_json(self) -> str:
        """Serialize to JSON string for transport."""
        return self.model_dump_json()

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        service: str,
        trace_id: Optional[str] = None,
    ) -> "ErrorEnvelope":
        """Convert any exception to an INT_ error envelope."""
        safe_service = service if service in _VALID_SERVICES else "agent"
        safe_message = str(exc)[:500]
        return cls(
            trace_id=trace_id or uuid.uuid4().hex,
            service=safe_service,
            code="INT_INVARIANT_BROKEN",
            retryable=False,
            http_status=500,
            message=safe_message,
        )


def _build_envelope(
    code: str,
    service: str,
    message: str,
    span_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    details: Optional[Dict[str, str]] = None,
    cause_chain: Optional[List[Dict[str, str]]] = None,
) -> ErrorEnvelope:
    """Internal builder with code-family defaults."""
    safe_service = service if service in _VALID_SERVICES else "agent"
    prefix = _resolve_code_prefix(code)
    return ErrorEnvelope(
        trace_id=trace_id or uuid.uuid4().hex,
        span_id=span_id or uuid.uuid4().hex[:16],
        service=safe_service,
        code=code,
        retryable=_RETRYABLE_DEFAULTS.get(prefix, False),
        http_status=_HTTP_STATUS_MAP.get(prefix, 500),
        message=message[:500],
        details=details,
        cause_chain=cause_chain,
    )


def val_error(
    code: str,
    message: str,
    service: str = "agent",
    **kwargs,
) -> ErrorEnvelope:
    """Validation error (retryable=False, HTTP 400)."""
    full_code = code if code.startswith("VAL_") else f"VAL_{code}"
    return _build_envelope(full_code, service, message, **kwargs)


def auth_error(
    code: str,
    message: str,
    service: str = "agent",
    **kwargs,
) -> ErrorEnvelope:
    """Auth error (retryable=False, HTTP 401/403)."""
    full_code = code if code.startswith("AUTH_") else f"AUTH_{code}"
    return _build_envelope(full_code, service, message, **kwargs)


def biz_error(
    code: str,
    message: str,
    service: str = "agent",
    **kwargs,
) -> ErrorEnvelope:
    """Business rule error (retryable=False, HTTP 422)."""
    full_code = code if code.startswith("BIZ_") else f"BIZ_{code}"
    return _build_envelope(full_code, service, message, **kwargs)


def dep_error(
    code: str,
    message: str,
    service: str = "agent",
    **kwargs,
) -> ErrorEnvelope:
    """Dependency error (retryable=True, HTTP 503)."""
    full_code = code if code.startswith("DEP_") else f"DEP_{code}"
    return _build_envelope(full_code, service, message, **kwargs)


def res_error(
    code: str,
    message: str,
    service: str = "agent",
    **kwargs,
) -> ErrorEnvelope:
    """Resource exhaustion error (retryable=True, HTTP 429)."""
    full_code = code if code.startswith("RES_") else f"RES_{code}"
    return _build_envelope(full_code, service, message, **kwargs)


def net_error(
    code: str,
    message: str,
    service: str = "agent",
    **kwargs,
) -> ErrorEnvelope:
    """Network/timeout error (retryable=True, HTTP 504)."""
    full_code = code if code.startswith("NET_") else f"NET_{code}"
    return _build_envelope(full_code, service, message, **kwargs)


def int_error(
    code: str,
    message: str,
    service: str = "agent",
    **kwargs,
) -> ErrorEnvelope:
    """Internal invariant error (retryable=False, HTTP 500, alert)."""
    full_code = code if code.startswith("INT_") else f"INT_{code}"
    return _build_envelope(full_code, service, message, **kwargs)


def should_retry(envelope: ErrorEnvelope) -> bool:
    """Check if an error envelope indicates retryability."""
    return envelope.retryable


class AppError(Exception):
    """Application error carrying an ErrorEnvelope."""

    def __init__(self, envelope: ErrorEnvelope) -> None:
        self.envelope = envelope
        super().__init__(envelope.message)
