"""
Read-Only Adapter for Atlas AI Observability Layer.
Bridges FastAPI endpoints with MemorySystem WITHOUT any mutation capability.
Governed by: C-G3-1 (Read-Only Absolute), Rule 12 (Minimal Blast Radius).
"""
from __future__ import annotations

import logging
from datetime import datetime

from intelligence.memory_system.integration.pipeline_hook import PipelineGovernanceHook
from intelligence.memory_system.models.memory_record import MemoryType
from intelligence.observability.schemas import (
    AuditEventResponse,
    CancelledSignalResponse,
    MemoryStatsResponse,
    PipelineHealthResponse,
)

logger = logging.getLogger(__name__)


class ReadOnlyAdapter:
    """
    Strict read-only bridge to the Memory System.
    NEVER exposes store(), delete(), capture(), or forget() methods.
    """

    @staticmethod
    def get_pipeline_health() -> PipelineHealthResponse:
        """Check system component initialization status."""
        hook_initialized = PipelineGovernanceHook._initialized
        memory_system = PipelineGovernanceHook._memory_system

        storage_backend = "uninitialized"
        if memory_system is not None:
            storage_cls = type(memory_system.kernel._storage).__name__
            storage_backend = storage_cls

        return PipelineHealthResponse(
            status="operational" if hook_initialized else "standby",
            memory_system_initialized=memory_system is not None,
            hook_initialized=hook_initialized,
            storage_backend=storage_backend,
            timestamp=datetime.now(),
        )

    @staticmethod
    def get_memory_stats() -> MemoryStatsResponse:
        """Aggregate memory tier statistics via read-only access."""
        memory_system = PipelineGovernanceHook._memory_system
        if memory_system is None:
            return MemoryStatsResponse(
                total_records=0, working_count=0,
                episodic_count=0, semantic_count=0, procedural_count=0,
            )

        # Use InMemoryStorage internal dict for counting
        # This is safe because we only READ from _store
        storage = memory_system.kernel._storage
        counts = {
            MemoryType.WORKING: 0,
            MemoryType.EPISODIC: 0,
            MemoryType.SEMANTIC: 0,
            MemoryType.PROCEDURAL: 0,
        }

        if hasattr(storage, "_store"):
            for record in storage._store.values():
                if record.memory_type in counts:
                    counts[record.memory_type] += 1

        total = sum(counts.values())
        return MemoryStatsResponse(
            total_records=total,
            working_count=counts[MemoryType.WORKING],
            episodic_count=counts[MemoryType.EPISODIC],
            semantic_count=counts[MemoryType.SEMANTIC],
            procedural_count=counts[MemoryType.PROCEDURAL],
        )

    @staticmethod
    def get_recent_audit_events(limit: int = 50) -> list[AuditEventResponse]:
        """Retrieve recent audit events with sensitive data stripped."""
        memory_system = PipelineGovernanceHook._memory_system
        if memory_system is None:
            return []

        from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
        audit_sink = memory_system.audit_sink

        if not isinstance(audit_sink, InMemoryAuditSink):
            return []

        events = audit_sink.events()
        recent = events[-limit:] if len(events) > limit else events

        result = []
        for e in recent:
            # C-G3-6: Strip sensitive metadata before exposing
            result.append(AuditEventResponse(
                event_id=e.event_id,
                event_type=e.event_type.value,
                operation_id=e.operation_id,
                agent_id=e.agent_id,
                timestamp=e.timestamp,
                action=e.action.value,
                resource=e.resource,
                result=e.result.value,
            ))
        return result

    @staticmethod
    def get_cancelled_signals(limit: int = 50) -> list[CancelledSignalResponse]:
        """Retrieve cancellation records from Working Memory."""
        memory_system = PipelineGovernanceHook._memory_system
        if memory_system is None:
            return []

        storage = memory_system.kernel._storage
        results = []

        if hasattr(storage, "_store"):
            for record in storage._store.values():
                if (
                    record.memory_type == MemoryType.WORKING
                    and isinstance(record.content, dict)
                    and record.content.get("event_type") == "signal_cancellation"
                ):
                    content = record.content
                    results.append(CancelledSignalResponse(
                        memory_id=record.memory_id,
                        symbol=str(content.get("symbol", "UNKNOWN")),
                        action=str(content.get("action", "UNKNOWN")),
                        decision=str(content.get("decision", "UNKNOWN")),
                        reason=str(content.get("reason", "UNKNOWN")),
                        survival_score=float(content.get("survival_score", 0.0)),
                        created_at=record.created_at,
                    ))

        # Return most recent first
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[:limit]
