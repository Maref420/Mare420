"""PRODUCTION VALIDATION: Memory subsystems type safety and retrieval.

Verifies that each memory store enforces its type boundary,
and that retrieval engine correctly serves all memory types.

Not synthetic. Tests real governance enforcement in each subsystem.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from intelligence.memory_system.episodic_memory.store import EpisodicMemoryStore
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)
from intelligence.memory_system.procedural_memory.store import ProceduralMemoryStore
from intelligence.memory_system.retrieval_engine.engine import MemoryRetrievalEngine
from intelligence.memory_system.semantic_memory.store import SemanticMemoryStore
from intelligence.memory_system.storage.interface import MemoryStorage
from intelligence.memory_system.working_memory.store import WorkingMemoryStore


class InMemoryStorage(MemoryStorage):
    def __init__(self) -> None:
        self.records: dict[str, MemoryRecord] = {}

    def store(self, record: MemoryRecord) -> None:
        self.records[record.memory_id] = record

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        return self.records.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        return self.records.pop(memory_id, None) is not None


def make_record(memory_id: str, memory_type: MemoryType) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=memory_type,
        created_at=datetime.now(timezone.utc),
        content={"test": True},
        metadata={},
        validation_status=ValidationStatus.VALIDATED,
        operation_id=f"op-{memory_id}",
        agent_id="agent-subsystem-test",
    )


# ============================================================
# Working Memory Store
# ============================================================
class TestWorkingMemoryStore:
    def test_accepts_working_type(self):
        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        store = WorkingMemoryStore(kernel)
        record = make_record("w-1", MemoryType.WORKING)
        store.store(record)
        assert storage.retrieve("w-1") is not None

    def test_rejects_non_working_type(self):
        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        store = WorkingMemoryStore(kernel)
        record = make_record("w-bad", MemoryType.EPISODIC)
        with pytest.raises(ValueError, match="working"):
            store.store(record)
        assert storage.retrieve("w-bad") is None

    def test_retrieve_returns_stored_record(self):
        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        store = WorkingMemoryStore(kernel)
        record = make_record("w-2", MemoryType.WORKING)
        store.store(record)
        retrieved = store.retrieve("w-2")
        assert retrieved is not None
        assert retrieved.memory_type == MemoryType.WORKING


# ============================================================
# Episodic Memory Store
# ============================================================
class TestEpisodicMemoryStore:
    def test_accepts_episodic_type(self):
        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        store = EpisodicMemoryStore(kernel)
        record = make_record("e-1", MemoryType.EPISODIC)
        store.store(record)
        assert storage.retrieve("e-1") is not None

    def test_rejects_non_episodic_type(self):
        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        store = EpisodicMemoryStore(kernel)
        record = make_record("e-bad", MemoryType.SEMANTIC)
        with pytest.raises(ValueError, match="episodic"):
            store.store(record)
        assert storage.retrieve("e-bad") is None


# ============================================================
# Semantic Memory Store
# ============================================================
class TestSemanticMemoryStore:
    def test_accepts_semantic_type(self):
        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        store = SemanticMemoryStore(kernel)
        record = make_record("s-1", MemoryType.SEMANTIC)
        store.store(record)
        assert storage.retrieve("s-1") is not None

    def test_rejects_non_semantic_type(self):
        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        store = SemanticMemoryStore(kernel)
        record = make_record("s-bad", MemoryType.PROCEDURAL)
        with pytest.raises(ValueError, match="semantic"):
            store.store(record)
        assert storage.retrieve("s-bad") is None


# ============================================================
# Procedural Memory Store
# ============================================================
class TestProceduralMemoryStore:
    def test_accepts_procedural_type(self):
        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        store = ProceduralMemoryStore(kernel)
        record = make_record("p-1", MemoryType.PROCEDURAL)
        store.store(record)
        assert storage.retrieve("p-1") is not None

    def test_rejects_non_procedural_type(self):
        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        store = ProceduralMemoryStore(kernel)
        record = make_record("p-bad", MemoryType.WORKING)
        with pytest.raises(ValueError, match="procedural"):
            store.store(record)
        assert storage.retrieve("p-bad") is None


# ============================================================
# Retrieval Engine
# ============================================================
class TestRetrievalEngine:
    def test_retrieves_all_valid_types(self):
        storage = InMemoryStorage()
        for mt in MemoryType:
            record = make_record(f"ret-{mt.value}", mt)
            storage.store(record)
        engine = MemoryRetrievalEngine(storage)
        for mt in MemoryType:
            result = engine.retrieve(f"ret-{mt.value}")
            assert result is not None, f"Failed to retrieve {mt.value}"
            assert result.memory_type == mt

    def test_returns_none_for_missing(self):
        storage = InMemoryStorage()
        engine = MemoryRetrievalEngine(storage)
        assert engine.retrieve("nonexistent") is None

    def test_rejects_empty_memory_id(self):
        storage = InMemoryStorage()
        engine = MemoryRetrievalEngine(storage)
        with pytest.raises(ValueError, match="empty"):
            engine.retrieve("")

    def test_cross_store_retrieval(self):
        """Records stored via typed stores are retrievable via retrieval engine."""
        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        w_store = WorkingMemoryStore(kernel)
        e_store = EpisodicMemoryStore(kernel)
        engine = MemoryRetrievalEngine(storage)

        w_store.store(make_record("cross-w", MemoryType.WORKING))
        e_store.store(make_record("cross-e", MemoryType.EPISODIC))

        assert engine.retrieve("cross-w") is not None
        assert engine.retrieve("cross-e") is not None
        assert engine.retrieve("cross-w").memory_type == MemoryType.WORKING
        assert engine.retrieve("cross-e").memory_type == MemoryType.EPISODIC
