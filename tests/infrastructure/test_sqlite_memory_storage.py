"""Tests for SqliteMemoryStorage — local SQLite persistence backend.

Governance: Tests verify MemoryStorage interface contract compliance.
No external services required (sqlite3 is stdlib).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)
from infrastructure.database.sqlite_memory_storage import SqliteMemoryStorage


def _make_record(
    memory_id: str = "mem-001",
    memory_type: MemoryType = MemoryType.EPISODIC,
    content: object = {"event": "test"},
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=memory_type,
        created_at=datetime.now(timezone.utc),
        content=content,
        metadata={"source": "test"},
        validation_status=ValidationStatus.VALIDATED,
        operation_id="op-001",
        agent_id="agent-001",
    )


@pytest.fixture
def db_path(tmp_path: pytest.TempPathFactory) -> str:
    return str(tmp_path / "test_memory.db")  # type: ignore[arg-type]


@pytest.fixture
def storage(db_path: str) -> SqliteMemoryStorage:
    with SqliteMemoryStorage(db_path) as s:
        yield s


class TestSqliteMemoryStorage:
    def test_store_and_retrieve(self, storage: SqliteMemoryStorage) -> None:
        record = _make_record()
        storage.store(record)
        result = storage.retrieve(record.memory_id)
        assert result is not None
        assert result.memory_id == record.memory_id
        assert result.memory_type == record.memory_type
        assert result.content == record.content
        assert result.agent_id == record.agent_id

    def test_retrieve_nonexistent_returns_none(self, storage: SqliteMemoryStorage) -> None:
        assert storage.retrieve("nonexistent-id") is None

    def test_upsert_overwrites(self, storage: SqliteMemoryStorage) -> None:
        r1 = _make_record(content={"version": 1})
        r2 = _make_record(content={"version": 2})
        storage.store(r1)
        storage.store(r2)
        result = storage.retrieve("mem-001")
        assert result is not None
        assert result.content == {"version": 2}

    def test_delete_existing(self, storage: SqliteMemoryStorage) -> None:
        storage.store(_make_record())
        assert storage.delete("mem-001") is True
        assert storage.retrieve("mem-001") is None

    def test_delete_nonexistent(self, storage: SqliteMemoryStorage) -> None:
        assert storage.delete("nonexistent") is False

    def test_durability_across_reopen(self, db_path: str) -> None:
        record = _make_record()
        with SqliteMemoryStorage(db_path) as s1:
            s1.store(record)
        with SqliteMemoryStorage(db_path) as s2:
            result = s2.retrieve(record.memory_id)
        assert result is not None
        assert result.memory_id == record.memory_id

    def test_multiple_memory_types(self, storage: SqliteMemoryStorage) -> None:
        for mt in MemoryType:
            r = _make_record(memory_id=f"mem-{mt.value}", memory_type=mt)
            storage.store(r)
        for mt in MemoryType:
            result = storage.retrieve(f"mem-{mt.value}")
            assert result is not None
            assert result.memory_type == mt

    def test_complex_content(self, storage: SqliteMemoryStorage) -> None:
        complex_data = {
            "nested": {"deep": [1, 2, 3]},
            "unicode": "سلام دنیا 🌍",
            "numbers": {"int": 42, "float": 3.14},
        }
        record = _make_record(content=complex_data)
        storage.store(record)
        result = storage.retrieve(record.memory_id)
        assert result is not None
        assert result.content == complex_data

    def test_context_manager_closes(self, db_path: str) -> None:
        with SqliteMemoryStorage(db_path) as s:
            s.store(_make_record())
        assert s._conn is None
