"""Production-grade structured JSON logger for Atlas AI Python services.

Governance compliance:
- Structured JSON output (one object per line)
- Required fields: service, trace_id, span_id, level, code, duration_ms, message, timestamp
- Context propagation via contextvars (thread-safe)
- Secret sanitization (key, secret, token, password, api_key)
- Configurable via LOG_LEVEL and LOG_SERVICE env vars
- No external dependencies (stdlib only)
"""
from __future__ import annotations

import contextvars
import datetime
import json
import logging
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from typing import Any, Generator, Optional

_TRACE_ID_CTX: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)
_SPAN_ID_CTX: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "span_id", default=None
)

_SECRET_PATTERN = re.compile(
    r"(?:key|secret|token|password|api_key)", re.IGNORECASE
)

_active_logger: Optional[logging.Logger] = None


def _sanitize_value(value: Any) -> Any:
    """Redact secrets from string values."""
    if isinstance(value, str):
        return _SECRET_PATTERN.sub("***REDACTED***", value)
    return value


def _sanitize_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Remove keys matching secret patterns and redact values."""
    result: dict[str, Any] = {}
    for k, v in d.items():
        if _SECRET_PATTERN.search(str(k)):
            continue
        result[k] = _sanitize_value(v)
    return result


class StructuredFormatter(logging.Formatter):
    """Format log records as single-line JSON with governance-required fields."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        msg = record.getMessage()
        if _SECRET_PATTERN.search(msg):
            msg = _SECRET_PATTERN.sub("***REDACTED***", msg)

        log_entry: dict[str, Any] = {
            "service": getattr(record, "service", None)
            or os.environ.get("LOG_SERVICE", "unknown"),
            "trace_id": getattr(record, "trace_id", None) or _TRACE_ID_CTX.get(),
            "span_id": getattr(record, "span_id", None) or _SPAN_ID_CTX.get(),
            "level": record.levelname,
            "code": getattr(record, "code", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "message": msg,
            "timestamp": ts,
        }

        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_entry["details"] = _sanitize_dict(record.extra_data)

        try:
            return json.dumps(log_entry, default=str, ensure_ascii=False)
        except Exception:
            return json.dumps(
                {"service": "logger", "message": "formatting_failed", "timestamp": ts},
                default=str,
            )


def _resolve_level(level_str: str) -> int:
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    resolved = levels.get(level_str.upper())
    if resolved is None:
        raise ValueError(f"Invalid LOG_LEVEL: {level_str}")
    return resolved


def setup_logger(service: str) -> logging.Logger:
    """Initialize structured logger for a service.

    Args:
        service: Service name (used in all log entries).

    Returns:
        Configured logger instance.
    """
    global _active_logger
    level_str = os.environ.get("LOG_LEVEL", "INFO")
    os.environ["LOG_SERVICE"] = service

    logger = logging.getLogger(service)
    logger.setLevel(_resolve_level(level_str))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)

    logger.propagate = False
    _active_logger = logger
    return logger


def get_trace_id() -> str:
    """Get current trace ID from context."""
    return _TRACE_ID_CTX.get() or ""


def set_trace_id(trace_id: str) -> None:
    """Set trace ID in current context (propagates to child calls)."""
    _TRACE_ID_CTX.set(trace_id)


@contextmanager
def new_span() -> Generator[str, None, None]:
    """Context manager that creates a new span ID for the enclosed block.

    Yields:
        The generated span_id string.
    """
    span_id = str(uuid.uuid4())[:16]
    token = _SPAN_ID_CTX.set(span_id)
    try:
        yield span_id
    finally:
        _SPAN_ID_CTX.reset(token)


@contextmanager
def timed(operation_name: str) -> Generator[None, None, None]:
    """Context manager that logs operation duration on exit.

    Args:
        operation_name: Human-readable name for the timed operation.
    """
    start = time.monotonic()
    try:
        yield
    finally:
        duration_ms = round((time.monotonic() - start) * 1000.0, 2)
        target = _active_logger or logging.getLogger(os.environ.get("LOG_SERVICE", "unknown"))
        record = target.makeRecord(
            name=target.name,
            level=logging.INFO,
            fn="",
            lno=0,
            msg=f"{operation_name} completed",
            args=(),
            exc_info=None,
        )
        record.duration_ms = duration_ms  # type: ignore[attr-defined]
        record.code = "SYS_PERF"  # type: ignore[attr-defined]
        target.handle(record)
