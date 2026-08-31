"""Strategy Signal Audit Logger.

Standalone module that bridges Strategy Signal Events to the Audit Sink.
This module is the ONLY place where strategy signal audit records are created.

Caller responsibility: call log_strategy_signal_received() after successful
from_json() or create(). This module does NOT hook into the adapter.

Governed by:
- contracts/schemas/audit/audit-storage-v1.json
- governance/policies/python-policy.yaml
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from intelligence.agent_control_plane.audit.models import (
    AuditAction,
    AuditEventType,
    AuditRecord,
    AuditResult,
)

if TYPE_CHECKING:
    from intelligence.strategy_intelligence.contract_adapter import (
        StrategySignalEventV1,
    )

logger = logging.getLogger(__name__)


def _get_sink():
    """Lazy-initialize SupabaseAuditSink to avoid import-time side effects."""
    from intelligence.agent_control_plane.audit.database_sink import (
        SupabaseAuditSink,
    )
    return SupabaseAuditSink()


def log_strategy_signal_received(
    raw_json: str,
    event: StrategySignalEventV1,
    operation_id: str = "",
) -> None:
    """Log a STRATEGY_SIGNAL_RECEIVED audit record.

    MUST be called after successful from_json() or create().
    Never raises exceptions — failures are logged but do not block the caller.

    Args:
        raw_json: Original immutable JSON payload.
        event: Deserialized and validated event.
        operation_id: Correlation ID for the operation (auto-generated if empty).
    """
    try:
        import uuid

        sink = _get_sink()
        record = AuditRecord(
            contract_version=event.version,
            event_id=event.event_id,
            event_type=AuditEventType.STRATEGY_SIGNAL_RECEIVED,
            operation_id=operation_id or str(uuid.uuid4()),
            agent_id=event.source_agent,
            timestamp=datetime.now(timezone.utc),
            action=AuditAction.COMPLETED,
            resource=f"strategy_signal:{event.event_id}",
            result=AuditResult.SUCCESS,
            metadata={
                "symbol": event.signal.symbol,
                "direction": event.signal.direction,
                "confidence": str(event.signal.confidence),
                "regime": event.signal.regime,
                "raw_payload": raw_json,
            },
        )
        sink.record(record)
    except Exception:
        logger.exception(
            "Failed to audit strategy signal %s",
            getattr(event, "event_id", "unknown"),
        )


def log_strategy_signal_rejected(
    raw_json: str,
    error: str,
    source_agent: str = "unknown",
    operation_id: str = "",
) -> None:
    """Log a STRATEGY_SIGNAL_RECEIVED audit record for REJECTED signals.

    Called when from_json() raises ContractValidationError.
    Ensures even failed signals have an audit trail.

    Args:
        raw_json: Original JSON payload (may be invalid).
        error: Error message describing rejection reason.
        source_agent: Agent name if parseable, else "unknown".
        operation_id: Correlation ID (auto-generated if empty).
    """
    try:
        import json
        import uuid

        sink = _get_sink()

        # Try to extract event_id from raw JSON even if validation failed
        event_id = "unknown"
        try:
            parsed = json.loads(raw_json)
            event_id = parsed.get("event_id", "unknown")
        except (json.JSONDecodeError, TypeError, KeyError):
            event_id = "unknown"  # explicit fallback for malformed JSON

        record = AuditRecord(
            contract_version="1.0.0",
            event_id=event_id,
            event_type=AuditEventType.STRATEGY_SIGNAL_RECEIVED,
            operation_id=operation_id or str(uuid.uuid4()),
            agent_id=source_agent,
            timestamp=datetime.now(timezone.utc),
            action=AuditAction.FAILED,
            resource=f"strategy_signal:{event_id}",
            result=AuditResult.FAILURE,
            metadata={
                "rejection_reason": error,
                "raw_payload": raw_json[:1000],  # truncate for safety
            },
        )
        sink.record(record)
    except Exception:
        logger.exception("Failed to audit rejected strategy signal")
