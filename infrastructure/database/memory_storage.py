import os

from intelligence.memory_system.models.memory_record import MemoryRecord
from intelligence.memory_system.storage.interface import MemoryStorage
from supabase import Client, create_client


class DatabaseMemoryStorage(MemoryStorage):
    """Supabase-backed persistent storage for validated memory records."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )

    def store(self, record: MemoryRecord) -> None:
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

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
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

    def delete(self, memory_id: str) -> bool:
        response = (
            self._client
            .table("memory_records")
            .delete()
            .eq("memory_id", memory_id)
            .execute()
        )

        return bool(response.data)
