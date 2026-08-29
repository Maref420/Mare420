"""Supabase-backed persistent storage for validated memory records.

Governed by: contracts/schemas/memory/memory-contract-v1.json
All database operations include error handling and graceful degradation.
"""
import logging
import os
from typing import Any

from intelligence.memory_system.models.memory_record import MemoryRecord
from intelligence.memory_system.storage.interface import MemoryStorage

logger = logging.getLogger(__name__)


class DatabaseMemoryStorage(MemoryStorage):
    """Supabase-backed persistent storage for validated memory records.

    Governed: All operations fail gracefully with logging.
    Connection errors never propagate to callers.
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
                    "are required for DatabaseMemoryStorage"
                )
            from supabase import create_client
            self._client = create_client(url, key)

    def store(self, record: MemoryRecord) -> None:
        """Store or update a memory record.

        Governed: Upsert with conflict resolution on memory_id.
        Failures are logged but do not propagate.
        """
        try:
            payload = {
                "memory_id": record.memory_id,
                "memory_type": record.memory_type.value,
                "created_at": record.created_at.isoformat(),
                "content": record.content,
                "metadata": record.metadata,
                "validation_status": record.validation_status.value,
                "operation_id": record.operation_id,
                "agent_id": record.agent_id,
            }
            self._client.table("memory_records").upsert(
                payload,
                on_conflict="memory_id",
            ).execute()
        except Exception:
            logger.exception(
                "Failed to store memory record %s", record.memory_id
            )

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a memory record by ID.

        Governed: Returns None on any failure (network, parse, missing).
        """
        try:
            response = (
                self._client
                .table("memory_records")
                .select(
                    "memory_id,memory_type,created_at,content,metadata,"
                    "validation_status,operation_id,agent_id"
                )
                .eq("memory_id", memory_id)
                .limit(1)
                .execute()
            )
            if not response.data:
                return None
            return MemoryRecord.model_validate(response.data[0])
        except Exception:
            logger.exception(
                "Failed to retrieve memory record %s", memory_id
            )
            return None

    def delete(self, memory_id: str) -> bool:
        """Delete a memory record by ID.

        Governed: Returns False on any failure.
        """
        try:
            response = (
                self._client
                .table("memory_records")
                .delete()
                .eq("memory_id", memory_id)
                .execute()
            )
            return bool(response.data)
        except Exception:
            logger.exception(
                "Failed to delete memory record %s", memory_id
            )
            return False
