"""PRODUCTION-GRADE Memory Lifecycle Validation.

Tests the FULL data lifecycle from creation to terminal state,
verifying governance enforcement at every stage.

Not unit tests. Not mocks for satisfaction. Real pipeline validation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
from intelligence.memory_system.consolidation.engine import MemoryConsolidationEngine
from intelligence.memory_system.forgetting.engine import MemoryForgettingEngine
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)
from intelligence.memory_system.storage.interface import MemoryStorage


class ProductionMemoryStorage(MemoryStorage):
    """Realistic in-memory storage that tracks all operations for verification."""

    def __init__(self) -> None:
        self.records: dict[str, MemoryRecord] = {}
        self.store_calls: list[str] = []
        self.delete_calls: list[str] = []

    def store(self, record: MemoryRecord) -> None:
        self.store_calls.append(record.memory_id)
        self.records[record.memory_id] = record

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        return self.records.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        self.delete_calls.append(memory_id)
        return self.records.pop(memory_id, None) is not None


def make_pipeline():
    storage = ProductionMemoryStorage()
    kernel = MemoryKernel(storage)
    audit = InMemoryAuditSink()
    consolidation = MemoryConsolidationEngine(kernel)
    forgetting = MemoryForgettingEngine(kernel, audit)
    return storage, kernel, audit, consolidation, forgetting


def make_episodic(memory_id: str, content: dict[str, Any] | None = None) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=MemoryType.EPISODIC,
        created_at=datetime.now(timezone.utc),
        content=content or {"trade": "BTCUSDT", "pnl": -150.0},
        metadata={"source": "execution_engine"},
        validation_status=ValidationStatus.VALIDATED,
        operation_id=f"op-create-{memory_id}",
        agent_id="agent-prod-lifecycle",
    )


# ============================================================
# PL1: Full lifecycle — create → store → consolidate → forget with policy
# ============================================================
def test_pl1_full_lifecycle_traceability():
    """Verify complete 5-stage lifecycle with full traceability chain."""
    storage, kernel, audit, consolidation, forgetting = make_pipeline()

    # Stage 1-2: Create validated episodic memory
    episodic = make_episodic("epi-prod-001")
    kernel.store(episodic)
    assert storage.retrieve("epi-prod-001") is not None, "Stage 2 failed: store rejected valid record"

    # Stage 5: Consolidate episodic → semantic
    semantic = consolidation.consolidate(
        episodic,
        operation_id="op-consolidate-001",
        agent_id="agent-prod-lifecycle",
    )
    assert semantic.memory_type == MemoryType.SEMANTIC
    assert semantic.metadata.get("consolidated_from") == "epi-prod-001", "Traceability lost in consolidation"
    assert storage.retrieve(semantic.memory_id) is not None, "Consolidated record not persisted"

    # Stage 6-7: Forget semantic WITH explicit policy
    deleted = forgetting.forget(
        semantic.memory_id,
        operation_id="op-forget-001",
        agent_id="agent-prod-lifecycle",
        explicit_policy_id="memory-lifecycle-policy:v1:manual-cleanup",
    )
    assert deleted is True, "Semantic with explicit policy should be deletable"
    assert storage.retrieve(semantic.memory_id) is None, "Record still exists after deletion"

    # Verify audit trail has entries for this lifecycle
    events = audit.events()
    forget_events = [e for e in events if e.resource == semantic.memory_id]
    assert len(forget_events) >= 1, "No audit events for semantic deletion"
    assert forget_events[-1].result.value == "success"
    print(f"✅ PL1 PASSED: Full lifecycle completed with {len(events)} audit events")


# ============================================================
# PL2: Semantic protection — forget without policy MUST fail
# ============================================================
def test_pl2_semantic_protection_in_real_pipeline():
    """Semantic memory created through real consolidation cannot be forgotten without policy."""
    storage, kernel, audit, consolidation, forgetting = make_pipeline()

    episodic = make_episodic("epi-prod-002")
    kernel.store(episodic)
    semantic = consolidation.consolidate(
        episodic,
        operation_id="op-consolidate-002",
        agent_id="agent-prod-lifecycle",
    )

    # Attempt forget WITHOUT explicit policy
    deleted = forgetting.forget(
        semantic.memory_id,
        operation_id="op-forget-denied",
        agent_id="agent-prod-lifecycle",
    )

    assert deleted is False, "Semantic MUST NOT be deleted without explicit policy"
    assert storage.retrieve(semantic.memory_id) is not None, "Semantic was deleted despite policy denial"

    events = audit.events()
    denial_events = [
        e for e in events
        if e.resource == semantic.memory_id and e.result.value == "failure"
    ]
    assert len(denial_events) >= 1, "Policy denial was not audited"
    assert "semantic_forgetting_requires_explicit_policy" in denial_events[-1].metadata.get("reason", "")
    print("✅ PL2 PASSED: Semantic protection enforced in real pipeline")


# ============================================================
# PL3: Working memory TTL — real time-based expiry
# ============================================================
def test_pl3_working_memory_ttl_lifecycle():
    """Working memory respects real expires_at timestamps."""
    storage, kernel, audit, _, forgetting = make_pipeline()

    # Create working memory that expired 1 second ago
    expired_time = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    working_expired = MemoryRecord(
        memory_id="work-expired-prod",
        memory_type=MemoryType.WORKING,
        created_at=datetime.now(timezone.utc),
        content={"context": "active_session"},
        metadata={"expires_at": expired_time},
        validation_status=ValidationStatus.VALIDATED,
        operation_id="op-create-working",
        agent_id="agent-prod-lifecycle",
    )
    kernel.store(working_expired)

    # Create working memory that expires in 1 hour
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    working_live = MemoryRecord(
        memory_id="work-live-prod",
        memory_type=MemoryType.WORKING,
        created_at=datetime.now(timezone.utc),
        content={"context": "active_session_2"},
        metadata={"expires_at": future_time},
        validation_status=ValidationStatus.VALIDATED,
        operation_id="op-create-working-2",
        agent_id="agent-prod-lifecycle",
    )
    kernel.store(working_live)

    # Expired one MUST be deleted
    deleted_expired = forgetting.forget_if_expired_working_memory(
        "work-expired-prod",
        operation_id="op-expire-check",
        agent_id="agent-prod-lifecycle",
    )
    assert deleted_expired is True, "Expired working memory should be auto-deleted"
    assert storage.retrieve("work-expired-prod") is None

    # Live one MUST be preserved
    deleted_live = forgetting.forget_if_expired_working_memory(
        "work-live-prod",
        operation_id="op-expire-check-2",
        agent_id="agent-prod-lifecycle",
    )
    assert deleted_live is False, "Non-expired working memory must be preserved"
    assert storage.retrieve("work-live-prod") is not None
    print("✅ PL3 PASSED: Working memory TTL lifecycle verified")


# ============================================================
# PL4: Audit trail integrity across full pipeline
# ============================================================
def test_pl4_audit_trail_integrity():
    """Every lifecycle operation produces correctly structured audit events."""
    storage, kernel, audit, consolidation, forgetting = make_pipeline()

    episodic = make_episodic("epi-audit-001")
    kernel.store(episodic)
    semantic = consolidation.consolidate(
        episodic,
        operation_id="op-audit-consolidate",
        agent_id="agent-audit-trace",
    )

    # Successful forget
    forgetting.forget(
        semantic.memory_id,
        operation_id="op-audit-forget-ok",
        agent_id="agent-audit-trace",
        explicit_policy_id="policy:test",
    )

    # Failed forget (no policy on new semantic)
    episodic2 = make_episodic("epi-audit-002")
    kernel.store(episodic2)
    semantic2 = consolidation.consolidate(
        episodic2,
        operation_id="op-audit-consolidate-2",
        agent_id="agent-audit-trace",
    )
    forgetting.forget(
        semantic2.memory_id,
        operation_id="op-audit-forget-denied",
        agent_id="agent-audit-trace",
    )

    events = audit.events()
    assert len(events) >= 2, f"Expected at least 2 audit events, got {len(events)}"

    # Verify structure of every event
    for event in events:
        assert event.contract_version == "1.0", f"Wrong contract_version: {event.contract_version}"
        assert event.operation_id, "operation_id missing"
        assert event.agent_id, "agent_id missing"
        assert event.timestamp is not None, "timestamp missing"
        assert event.resource, "resource missing"
        assert event.result.value in ("success", "failure"), f"Invalid result: {event.result.value}"

    success_events = [e for e in events if e.result.value == "success"]
    failure_events = [e for e in events if e.result.value == "failure"]
    assert len(success_events) >= 1, "No successful audit events found"
    assert len(failure_events) >= 1, "No failure audit events found"
    print(f"✅ PL4 PASSED: {len(events)} audit events verified ({len(success_events)} success, {len(failure_events)} failure)")


# ============================================================
# PL5: Rejection at birth — invalid memory never reaches storage
# ============================================================
def test_pl5_rejection_at_birth():
    """Pending and rejected memories are rejected by kernel.store() before reaching storage."""
    storage, kernel, _, _, _ = make_pipeline()

    pending = MemoryRecord(
        memory_id="pending-reject",
        memory_type=MemoryType.EPISODIC,
        created_at=datetime.now(timezone.utc),
        content={"test": True},
        metadata={},
        validation_status=ValidationStatus.PENDING,
        operation_id="op-pending",
        agent_id="agent-reject",
    )

    rejected = MemoryRecord(
        memory_id="rejected-reject",
        memory_type=MemoryType.EPISODIC,
        created_at=datetime.now(timezone.utc),
        content={"test": True},
        metadata={},
        validation_status=ValidationStatus.REJECTED,
        operation_id="op-rejected",
        agent_id="agent-reject",
    )

    try:
        kernel.store(pending)
        assert False, "kernel.store() should reject PENDING memory"
    except ValueError as e:
        msg = str(e).lower()
        assert "validated" in msg or "rejected" in msg or "persist" in msg, f"Wrong error message: {e}"

    try:
        kernel.store(rejected)
        assert False, "kernel.store() should reject REJECTED memory"
    except ValueError as e:
        msg = str(e).lower()
        assert "validated" in msg or "rejected" in msg or "persist" in msg, f"Wrong error message: {e}"

    assert storage.retrieve("pending-reject") is None, "PENDING memory leaked into storage"
    assert storage.retrieve("rejected-reject") is None, "REJECTED memory leaked into storage"
    assert len(storage.store_calls) == 0, "Storage.store() was called for invalid records"
    print("✅ PL5 PASSED: Rejection at birth verified — no invalid memory in storage")
