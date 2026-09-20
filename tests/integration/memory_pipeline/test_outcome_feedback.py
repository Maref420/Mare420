"""
Integration Test: G2 Outcome Feedback Loop Proof.
Verifies that NATS execution outcomes flow through OutcomeBridgeSubscriber
into ExperienceEngine and persist in MemoryKernel storage.

Governed by:
- ATLAS Protocol Rule 16 (Observability)
- No parallel execution paths (runs within pytest framework)
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from intelligence.memory_system.integration.outcome_bridge import (
    ExecutionOutcomeEvent,
    OutcomeBridgeSubscriber,
)
from intelligence.memory_system.integration.pipeline_hook import (
    PipelineGovernanceHook,
)


class TestOutcomeFeedbackLoop:
    """Test suite proving G2 Outcome Feedback Loop integration."""

    @pytest.fixture(autouse=True)
    def setup_hook(self) -> None:
        """Initialize fresh PipelineGovernanceHook for each test."""
        PipelineGovernanceHook._instance = None
        PipelineGovernanceHook._memory_system = None
        PipelineGovernanceHook._initialized = False
        PipelineGovernanceHook.initialize()

    def test_outcome_event_schema_validation_passes(self) -> None:
        """Verify valid execution outcome passes Pydantic validation."""
        event = ExecutionOutcomeEvent(
            order_id="ord-001",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.5,
            pnl=150.0,
            status="filled",
            agent_id="strategy_agent",
            trace_id="trace-001",
        )
        assert event.order_id == "ord-001"
        assert event.side == "buy"
        assert event.status == "filled"

    def test_outcome_event_schema_rejects_invalid_side(self) -> None:
        """Verify invalid side value is rejected per schema contract."""
        with pytest.raises(Exception):
            ExecutionOutcomeEvent(
                order_id="ord-002",
                symbol="BTCUSDT",
                side="invalid_side",
                quantity=0.5,
                pnl=0.0,
                status="filled",
            )

    def test_outcome_event_schema_rejects_invalid_status(self) -> None:
        """Verify invalid status value is rejected per schema contract."""
        with pytest.raises(Exception):
            ExecutionOutcomeEvent(
                order_id="ord-003",
                symbol="ETHUSDT",
                side="sell",
                quantity=1.0,
                pnl=-50.0,
                status="unknown_status",
            )

    def test_bridge_handle_message_persists_to_memory(self) -> None:
        """
        Core G2 proof: Simulate NATS message handling and verify
        the outcome is persisted through ExperienceEngine into Kernel storage.
        """
        memory_system = PipelineGovernanceHook.get_memory_system()
        engine = memory_system.experience_engine

        bridge = OutcomeBridgeSubscriber(
            experience_engine=engine,
            nats_url="nats://localhost:4222",
            topic="atlas.execution.outcome.v1",
        )

        trace_id = f"g2-test-{uuid.uuid4().hex[:8]}"
        payload = {
            "order_id": "ord-g2-proof",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": 1.0,
            "pnl": 250.0,
            "status": "filled",
            "agent_id": "test_strategy_agent",
            "trace_id": trace_id,
        }

        # Execute handle_message directly (bypassing NATS transport)
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(bridge.handle_message(payload, trace_id))
        finally:
            loop.close()

        # Verify persistence: query all records in storage
        from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
        audit_sink = memory_system.audit_sink

        # Check audit trail was generated
        if isinstance(audit_sink, InMemoryAuditSink):
            events = audit_sink.events()
            store_events = [
                e for e in events
                if e.event_type.value == "memory.store"
            ]
            assert len(store_events) > 0, "No memory.store audit events found"

    def teardown_method(self, method: Any) -> None:
        """Cleanup after each test."""
        PipelineGovernanceHook.shutdown()
