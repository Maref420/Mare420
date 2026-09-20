"""
Supabase Persistent Storage Implementation for Atlas AI Memory Layer.
Implements MemoryStorage ABC using Supabase PostgreSQL backend.

Governed by:
- ATLAS Protocol Rule 12 (Minimal Blast Radius)
- lifecycle-policy.yaml: direct_storage_access: prohibited
  (This class IS the authorized storage boundary)
- Governance Rule 10: Frozen models preserved through serialization
"""
from __future__ import annotations

import logging
from typing import Any, cast

from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)

# Lazy resolve EpistemicStatus to handle export variations
try:
    from intelligence.contracts.unified_decision_proposal import EpistemicStatus
except ImportError:
    from intelligence.contracts.unified_decision_proposal import EpistemicStatus
from intelligence.memory_system.storage.interface import MemoryStorage

logger = logging.getLogger(__name__)

# Lazy import to prevent crash if supabase is not installed
try:
    from supabase import Client, create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = Any  # type: ignore[assignment,misc]


TABLE_NAME = "atlas_memory"


class SupabaseStorage(MemoryStorage):
    """
    Persistent storage backend using Supabase PostgreSQL.
    Implements exact MemoryStorage ABC contract: store, retrieve, delete.

    Thread-safe for single-process usage. All operations are synchronous
    as required by the ABC. Caller must use asyncio.to_thread() when
    invoking from async context to prevent event loop blocking.
    """

    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        if not SUPABASE_AVAILABLE:
            raise RuntimeError(
                "supabase package not installed. "
                "Run: pip install 'supabase>=2.31.0,<3.0'"
            )
        if not supabase_url or not supabase_key:
            raise ValueError("supabase_url and supabase_key must not be empty")

        self._client: Client = create_client(supabase_url, supabase_key)
        logger.info("SUPABASE_STORAGE_INITIALIZED")

    def store(self, record: MemoryRecord) -> None:
        """
        Persist a memory record to Supabase.

        Governed by: lifecycle-policy.yaml -> operations.store.validation_required
        Note: Kernel validates BEFORE calling this method. This is pure persistence.
        """
        try:
            payload = self._serialize_record(record)

            # Upsert: insert or update if memory_id already exists
            self._client.table(TABLE_NAME).upsert(
                payload, on_conflict="memory_id"
            ).execute()

            logger.info(
                "SUPABASE_STORE_SUCCESS",
                extra={"memory_id": record.memory_id, "type": record.memory_type.value},
            )
        except Exception as e:
            logger.error(
                "SUPABASE_STORE_FAILED",
                extra={"memory_id": record.memory_id, "error": str(e)},
            )
            raise

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a memory record by identifier from Supabase."""
        if not memory_id:
            raise ValueError("memory_id must not be empty.")

        try:
            response = (
                self._client.table(TABLE_NAME)
                .select("*")
                .eq("memory_id", memory_id)
                .limit(1)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                return None

            raw_row = response.data[0]
            row = cast(dict[str, Any], raw_row)
            record = self._deserialize_record(row)

            logger.info(
                "SUPABASE_RETRIEVE_SUCCESS",
                extra={"memory_id": memory_id},
            )
            return record

        except Exception as e:
            logger.error(
                "SUPABASE_RETRIEVE_FAILED",
                extra={"memory_id": memory_id, "error": str(e)},
            )
            raise

    def delete(self, memory_id: str) -> bool:
        """Delete a memory record when lifecycle policy permits it."""
        if not memory_id:
            raise ValueError("memory_id must not be empty.")

        try:
            response = (
                self._client.table(TABLE_NAME)
                .delete()
                .eq("memory_id", memory_id)
                .execute()
            )

            deleted = bool(response.data and len(response.data) > 0)

            if deleted:
                logger.info(
                    "SUPABASE_DELETE_SUCCESS",
                    extra={"memory_id": memory_id},
                )
            else:
                logger.warning(
                    "SUPABASE_DELETE_NOT_FOUND",
                    extra={"memory_id": memory_id},
                )

            return deleted

        except Exception as e:
            logger.error(
                "SUPABASE_DELETE_FAILED",
                extra={"memory_id": memory_id, "error": str(e)},
            )
            raise

    @staticmethod
    def _serialize_record(record: MemoryRecord) -> dict[str, Any]:
        """
        Convert frozen Pydantic MemoryRecord to Supabase-compatible dict.
        Handles Enum serialization and JSONB field preparation.
        """
        return {
            "memory_id": record.memory_id,
            "memory_type": record.memory_type.value,
            "created_at": record.created_at.isoformat(),
            "content": record.content,
            "metadata": record.metadata,
            "validation_status": record.validation_status.value,
            "operation_id": record.operation_id,
            "agent_id": record.agent_id,
            "source": record.source,
            "source_type": record.source_type,
            "regime": record.regime,
            "evidence_refs": record.evidence_refs,
            "epistemic_status": record.epistemic_status.value,
        }

    @staticmethod
    def _deserialize_record(row: dict[str, Any]) -> MemoryRecord:
        """
        Convert Supabase row back to frozen Pydantic MemoryRecord.
        Handles Enum deserialization and type coercion.
        """
        from datetime import datetime

        created_at_raw = row.get("created_at", "")
        if isinstance(created_at_raw, str):
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        else:
            created_at = created_at_raw

        return MemoryRecord(
            memory_id=row["memory_id"],
            memory_type=MemoryType(row["memory_type"]),
            created_at=created_at,
            content=row.get("content", {}),
            metadata=row.get("metadata", {}),
            validation_status=ValidationStatus(row["validation_status"]),
            operation_id=row["operation_id"],
            agent_id=row["agent_id"],
            source=row.get("source", "UNKNOWN_SOURCE"),
            source_type=row.get("source_type", "UNKNOWN_TYPE"),
            regime=row.get("regime", "UNKNOWN_REGIME"),
            evidence_refs=row.get("evidence_refs", []),
            epistemic_status=EpistemicStatus(
                row.get("epistemic_status", "unknown")
            ),
        )
