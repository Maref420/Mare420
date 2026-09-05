from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict

from intelligence.agent_control_plane.audit.models import AuditResult
from intelligence.memory_system.forgetting.engine import MemoryForgettingEngine
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)
from intelligence.memory_system.storage.interface import MemoryStorage


class InMemoryStorage(MemoryStorage):
    def __init__(self) -> None:
        self.records: Dict[str, MemoryRecord] = {}
        self.fail_delete = False

    def store(self, record: MemoryRecord) -> None:
        self.records[record.memory_id] = record

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        return self.records.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        if self.fail_delete:
            return False
        return self.records.pop(memory_id, None) is not None


class FakeAuditSink:
    def __init__(self) -> None:
        self.records = []

    def record(self, record) -> None:
        self.records.append(record)


def make_memory(
    memory_id: str,
    memory_type: MemoryType,
    metadata: dict | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=memory_type,
        created_at=datetime.now(timezone.utc),
        content={"value": "real-memory-content"},
        metadata=metadata or {},
        validation_status=ValidationStatus.VALIDATED,
        operation_id="op-create",
        agent_id="agent-lifecycle",
    )


def make_engine() -> tuple[MemoryForgettingEngine, InMemoryStorage, FakeAuditSink]:
    storage = InMemoryStorage()
    kernel = MemoryKernel(storage)
    audit = FakeAuditSink()
    engine = MemoryForgettingEngine(kernel, audit)
    return engine, storage, audit


def test_semantic_memory_cannot_be_forgotten_without_explicit_policy():
    engine, storage, audit = make_engine()
    storage.store(make_memory("sem-1", MemoryType.SEMANTIC))

    deleted = engine.forget(
        "sem-1",
        operation_id="op-forget",
        agent_id="agent-lifecycle",
    )

    assert deleted is False
    assert storage.retrieve("sem-1") is not None
    assert audit.records[-1].result == AuditResult.FAILURE
    assert audit.records[-1].metadata["reason"] == (
        "semantic_forgetting_requires_explicit_policy"
    )


def test_semantic_memory_can_be_forgotten_with_explicit_policy():
    engine, storage, audit = make_engine()
    storage.store(make_memory("sem-2", MemoryType.SEMANTIC))

    deleted = engine.forget(
        "sem-2",
        operation_id="op-forget",
        agent_id="agent-lifecycle",
        explicit_policy_id="memory-lifecycle-policy:v1:manual-semantic-removal",
    )

    assert deleted is True
    assert storage.retrieve("sem-2") is None
    assert audit.records[-1].result == AuditResult.SUCCESS
    assert audit.records[-1].metadata["memory_type"] == "semantic"


def test_expired_working_memory_is_automatically_forgotten():
    engine, storage, audit = make_engine()
    expired = datetime.now(timezone.utc) - timedelta(seconds=5)
    storage.store(
        make_memory(
            "work-expired",
            MemoryType.WORKING,
            metadata={"expires_at": expired.isoformat()},
        )
    )

    deleted = engine.forget_if_expired_working_memory(
        "work-expired",
        operation_id="op-expire",
        agent_id="agent-lifecycle",
    )

    assert deleted is True
    assert storage.retrieve("work-expired") is None
    assert audit.records[-1].result == AuditResult.SUCCESS
    assert audit.records[-1].metadata["automatic"] is True


def test_unexpired_working_memory_is_preserved():
    engine, storage, audit = make_engine()
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    storage.store(
        make_memory(
            "work-live",
            MemoryType.WORKING,
            metadata={"expires_at": future.isoformat()},
        )
    )

    deleted = engine.forget_if_expired_working_memory(
        "work-live",
        operation_id="op-expire",
        agent_id="agent-lifecycle",
    )

    assert deleted is False
    assert storage.retrieve("work-live") is not None
    assert audit.records == []


def test_failed_storage_delete_is_audited_as_failure_not_success():
    engine, storage, audit = make_engine()
    storage.store(make_memory("epi-1", MemoryType.EPISODIC))
    storage.fail_delete = True

    deleted = engine.forget(
        "epi-1",
        operation_id="op-forget",
        agent_id="agent-lifecycle",
        explicit_policy_id="memory-lifecycle-policy:v1:episodic-cleanup",
    )

    assert deleted is False
    assert storage.retrieve("epi-1") is not None
    assert audit.records[-1].result == AuditResult.FAILURE
    assert audit.records[-1].metadata["reason"] == "storage_delete_returned_false"
