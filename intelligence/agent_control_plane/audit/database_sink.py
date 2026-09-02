"""
Immutable audit event persistence sink for the agent control plane.

This module provides a write-once, idempotent persistence layer for
strategy-signal audit events to the Supabase `audit_events` table.
It performs no processing, transformation, or decision-making on the
payload; it only validates and persists immutable records.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Final, Optional

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator
from supabase import Client, create_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTRACT_VERSION: Final[str] = "1.0.0"
MAX_RETRIES: Final[int] = 3
BACKOFF_BASE_SECONDS: Final[float] = 0.1
BACKOFF_MULTIPLIER: Final[float] = 2.0

VALID_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "STRATEGY_SIGNAL_RECEIVED",
        "STRATEGY_SIGNAL_EXECUTED",
        "RISK_ASSESSMENT",
    }
)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AuditError(Exception):
    """Base exception for audit sink failures."""

    def __init__(self, message: str, *, cause: Optional[Exception] = None) -> None:
        self.message = message
        self.cause = cause
        super().__init__(message)


class AuditValidationError(AuditError):
    """Raised when an AuditRecord fails validation."""


class AuditPersistenceError(AuditError):
    """Raised when persistence to the audit store fails after all retries."""


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class AuditRecord(BaseModel):
    """
    Immutable audit event record.

    Attributes:
        event_id: Unique identifier for the audit event.
        event_type: Type of audit event. Must be one of the valid event types.
        resource: Resource identifier in the format "strategy_signal:{event_id}".
        payload: Arbitrary JSON-serializable payload. Must not contain secrets.
        timestamp: ISO-8601 timestamp of when the event occurred.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(..., min_length=1, max_length=255)
    event_type: str = Field(..., min_length=1, max_length=64)
    resource: str = Field(..., min_length=1, max_length=512)
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(..., description="ISO-8601 timestamp")

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """Ensure event_type is one of the allowed values."""
        if v not in VALID_EVENT_TYPES:
            raise ValueError(
                f"event_type must be one of {sorted(VALID_EVENT_TYPES)}, got '{v}'"
            )
        return v

    @field_validator("resource")
    @classmethod
    def validate_resource_format(cls, v: str) -> str:
        """Ensure resource follows the 'strategy_signal:{event_id}' format."""
        if not v.startswith("strategy_signal:"):
            raise ValueError(
                "resource must start with 'strategy_signal:' prefix"
            )
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: datetime) -> datetime:
        """Ensure timestamp is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return v


# ---------------------------------------------------------------------------
# Audit Sink
# ---------------------------------------------------------------------------


class AuditSink:
    """
    Immutable audit event persistence sink.

    Persists AuditRecord instances to the Supabase `audit_events` table
    in a write-once, idempotent manner. Duplicate event_ids are skipped
    silently. Failures are retried with exponential backoff and never
    block the calling pipeline.
    """

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        *,
        table_name: str = "audit_events",
        logger: Optional[structlog.stdlib.BoundLogger] = None,
    ) -> None:
        """
        Initialize the AuditSink.

        Args:
            supabase_url: Supabase project URL.
            supabase_key: Supabase service role or anon key with write access.
            table_name: Name of the audit events table. Defaults to 'audit_events'.
            logger: Optional structlog logger instance. If not provided, a
                default structlog logger is created.
        """
        self._table_name: Final[str] = table_name
        self._logger: structlog.stdlib.BoundLogger = (
            logger
            if logger is not None
            else structlog.get_logger("audit_sink")
        )

        try:
            self._client: Client = create_client(supabase_url, supabase_key)
        except Exception as exc:
            raise AuditError(
                "Failed to initialize Supabase client",
                cause=exc,
            ) from exc

        self._logger.info(
            "audit_sink_initialized",
            table_name=self._table_name,
            contract_version=CONTRACT_VERSION,
        )

    async def record(self, event: AuditRecord) -> None:
        """
        Persist an audit event to the immutable audit store.

        This method is idempotent: if an event with the same event_id
        already exists, the write is skipped silently. Failures are
        retried up to MAX_RETRIES times with exponential backoff.
        The method never raises on persistence failure; it logs the
        error and returns, ensuring the calling pipeline is never blocked.

        Args:
            event: The validated AuditRecord to persist.

        Raises:
            AuditValidationError: If the event fails Pydantic validation
                (should not occur if event is already an AuditRecord instance).
        """
        # Validate the input (defensive; AuditRecord is frozen so this
        # catches any mutation attempts or invalid construction).
        try:
            validated_event = AuditRecord.model_validate(event)
        except Exception as exc:
            raise AuditValidationError(
                f"Failed to validate AuditRecord: {exc}",
                cause=exc,
            ) from exc

        event_id: str = validated_event.event_id
        event_type: str = validated_event.event_type
        resource: str = validated_event.resource
        payload: dict[str, Any] = validated_event.payload
        timestamp: str = validated_event.timestamp.isoformat()

        self._logger.debug(
            "audit_record_attempt",
            event_id=event_id,
            event_type=event_type,
            resource=resource,
            contract_version=CONTRACT_VERSION,
        )

        last_exception: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await self._persist_event(
                    event_id=event_id,
                    event_type=event_type,
                    resource=resource,
                    payload=payload,
                    timestamp=timestamp,
                )
                self._logger.info(
                    "audit_record_persisted",
                    event_id=event_id,
                    event_type=event_type,
                    attempt=attempt,
                )
                return

            except AuditDuplicateError:
                # Idempotent skip: duplicate event_id already exists.
                self._logger.debug(
                    "audit_record_duplicate_skipped",
                    event_id=event_id,
                    event_type=event_type,
                )
                return

            except Exception as exc:
                last_exception = exc
                self._logger.warning(
                    "audit_record_persist_failed",
                    event_id=event_id,
                    event_type=event_type,
                    attempt=attempt,
                    max_retries=MAX_RETRIES,
                    error=str(exc),
                )

                if attempt < MAX_RETRIES:
                    backoff = BACKOFF_BASE_SECONDS * (
                        BACKOFF_MULTIPLIER ** (attempt - 1)
                    )
                    await asyncio.sleep(backoff)

        # All retries exhausted. Log the final failure but do NOT raise,
        # to ensure the pipeline is never blocked.
        self._logger.error(
            "audit_record_persist_permanent_failure",
            event_id=event_id,
            event_type=event_type,
            max_retries=MAX_RETRIES,
            error=str(last_exception) if last_exception else "unknown",
        )

    async def _persist_event(
        self,
        *,
        event_id: str,
        event_type: str,
        resource: str,
        payload: dict[str, Any],
        timestamp: str,
    ) -> None:
        """
        Perform the actual write to the Supabase audit_events table.

        Uses an upsert with on_conflict on event_id to achieve idempotency.
        If the row already exists, the operation is a no-op (skip silently).

        Args:
            event_id: Unique event identifier.
            event_type: Type of the audit event.
            resource: Resource