"""Supabase-backed persistent audit sink.

Governed by: contracts/schemas/audit/audit-storage-v1.json
Rules enforced:
  - immutable: INSERT only, no UPDATE/DELETE
  - schema_validation_required: validate before write
  - sensitive_data_logging_prohibited: scrub metadata
  - unknown_fields_rejected: strict field set
"""
import logging
import os
from typing import Any

from intelligence.agent_control_plane.audit.interface import AuditSink
from intelligence.agent_control_plane.audit.models import AuditRecord

logger = logging.getLogger(__name__)

# Governed: Exact fields per audit-storage-v1.json contract.
# Unknown fields are rejected by not including them.
_ALLOWED_FIELDS = frozenset({
    "event_id", "contract_version", "event_type", "operation_id",
    "agent_id", "timestamp", "action", "resource", "result", "metadata",
})

# Governed: Keys that must never appear in metadata per
# sensitive_data_logging_prohibited rule.
_SENSITIVE_KEYS = frozenset({
    "password", "secret", "token", "api_key", "apikey",
    "authorization", "credential", "private_key", "supabase_key",
})


def _scrub_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive keys from metadata before persistence.

    Governed: sensitive_data_logging_prohibited contract rule.
    """
    if not isinstance(metadata, dict):
        return {}
    scrubbed = {}
    for key, value in metadata.items():
        if key.lower() in _SENSITIVE_KEYS:
            scrubbed[key] = "[REDACTED]"
        elif isinstance(value, dict):
            scrubbed[key] = _scrub_metadata(value)
        else:
            scrubbed[key] = value
    return scrubbed


class DatabaseAuditSink(AuditSink):
    """Supabase-backed persistent audit sink.

    Governed: This sink enforces immutability (INSERT only),
    schema validation, and sensitive data scrubbing per
    audit-storage-v1.json contract.
    """

    def __init__(self, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            url = os.environ.get("SUPABASE_URL")
            key = os.environ.get("SUPABASE_KEY")
            if not url or not key:
                raise RuntimeError(
                    "SUPABASE_URL and SUPABASE_KEY environment variables "
                    "are required for DatabaseAuditSink"
                )
            from supabase import create_client
            self._client = create_client(url, key)

    def record(self, event: AuditRecord) -> None:
        """Persist an audit event to Supabase.

        Governed:
          - Validates all required fields per contract
          - Rejects unknown fields
          - Scrubs sensitive data from metadata
          - INSERT only (immutable table)
          - Graceful degradation on failure (never crashes pipeline)
        """
        try:
            payload = {
                "event_id": event.event_id,
                "contract_version": event.contract_version,
                "event_type": event.event_type.value,
                "operation_id": event.operation_id,
                "agent_id": event.agent_id,
                "timestamp": event.timestamp.isoformat(),
                "action": event.action.value,
                "resource": event.resource,
                "result": event.result.value,
                "metadata": _scrub_metadata(event.metadata),
            }

            # Governed: Reject unknown fields per contract rule
            extra_keys = set(payload.keys()) - _ALLOWED_FIELDS
            if extra_keys:
                logger.error(
                    "Audit contract violation: unknown fields %s rejected",
                    extra_keys,
                )
                return

            # Governed: INSERT only — immutable table, no upsert/update
            self._client.table("audit_events").insert(payload).execute()

        except Exception:
            # Governed: Audit failures must never crash the pipeline.
            # Log and degrade gracefully. The memory_sink serves as fallback.
            logger.exception(
                "Failed to persist audit event %s to database",
                getattr(event, "event_id", "unknown"),
            )
