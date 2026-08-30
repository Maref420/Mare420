"""Production tests for ExperienceEngine and MemoryEventSubscriber.

Verifies:
- Capture produces valid Episodic MemoryRecord
- Record stored via MemoryKernel (not direct storage)
- Audit trail created on every capture
- Input validation enforced
- Subscriber routes events correctly
"""
from __future__ import annotations

import pytest

from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
from intelligence.agent_control_plane.audit.models import AuditResult
from intelligence.memory_system.experience_engine.engine import ExperienceEngine
from intelligence.memory_system.experience_engine.subscriber import MemoryEventSubscriber
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import MemoryType, ValidationStatus
from intelligence.memory_system.storage.interface import MemoryStorage


class TrackingStorage(MemoryStorage):
    """Storage that tracks all operations for verification."""

    def __init__(self) -> None:
        self.records: dict = {}
        self.store_count = 0

    def store(self, record):
        self.store_count += 1
        self.records[record.memory_id] = record

    def retrieve(self, memory_id):
        return self.records.get(memory_id)

    def delete(self, memory_id):
        return self.records.pop(memory_id, None) is not None


def make_engine():
    storage = TrackingStorage()
    kernel = MemoryKernel(storage)
    audit = InMemoryAuditSink()
    engine = ExperienceEngine(kernel, audit)
    return engine, storage, audit


class TestExecutionOutcomeCapture:
    def test_produces_episodic_record(self):
        engine, storage, _ = make_engine()
        record = engine.capture_execution_outcome(
            order_id="ord-001", symbol="BTCUSDT", side="buy",
            quantity=1.5, pnl=-150.0, status="filled",
            agent_id="agent-test", operation_id="op-001",
        )
        assert record.memory_type == MemoryType.EPISODIC
        assert record.validation_status == ValidationStatus.VALIDATED
        assert record.content["event_type"] == "execution_outcome"
        assert storage.store_count == 1

    def test_audit_created_on_success(self):
        engine, _, audit = make_engine()
        engine.capture_execution_outcome(
            order_id="ord-002", symbol="ETHUSDT", side="sell",
            quantity=10.0, pnl=500.0, status="filled",
            agent_id="agent-test", operation_id="op-002",
        )
        events = audit.events()
        assert len(events) == 1
        assert events[0].result == AuditResult.SUCCESS
        assert events[0].metadata["source"] == "experience_engine"

    def test_invalid_side_rejected(self):
        engine, _, _ = make_engine()
        with pytest.raises(ValueError, match="side"):
            engine.capture_execution_outcome(
                order_id="ord-003", symbol="BTCUSDT", side="invalid",
                quantity=1.0, pnl=0.0, status="filled",
                agent_id="agent-test", operation_id="op-003",
            )

    def test_invalid_status_rejected(self):
        engine, _, _ = make_engine()
        with pytest.raises(ValueError, match="status"):
            engine.capture_execution_outcome(
                order_id="ord-004", symbol="BTCUSDT", side="buy",
                quantity=1.0, pnl=0.0, status="unknown_status",
                agent_id="agent-test", operation_id="op-004",
            )


class TestRiskAssessmentCapture:
    def test_produces_episodic_record(self):
        engine, storage, _ = make_engine()
        record = engine.capture_risk_assessment(
            assessment_type="position_limit", result="pass",
            circuit_breaker_state="normal", risk_score=42.0,
            agent_id="agent-test", operation_id="op-005",
        )
        assert record.memory_type == MemoryType.EPISODIC
        assert record.content["event_type"] == "risk_assessment"
        assert storage.store_count == 1

    def test_invalid_result_rejected(self):
        engine, _, _ = make_engine()
        with pytest.raises(ValueError, match="result"):
            engine.capture_risk_assessment(
                assessment_type="test", result="invalid",
                circuit_breaker_state="normal", risk_score=50.0,
                agent_id="agent-test", operation_id="op-006",
            )

    def test_risk_score_out_of_range_rejected(self):
        engine, _, _ = make_engine()
        with pytest.raises(ValueError, match="risk_score"):
            engine.capture_risk_assessment(
                assessment_type="test", result="pass",
                circuit_breaker_state="normal", risk_score=150.0,
                agent_id="agent-test", operation_id="op-007",
            )


class TestAgentDecisionCapture:
    def test_produces_episodic_record(self):
        engine, storage, _ = make_engine()
        record = engine.capture_agent_decision(
            decision_type="entry_signal", input_summary="RSI oversold",
            output_action="buy_limit", confidence=0.82,
            agent_id="agent-test", operation_id="op-008",
        )
        assert record.memory_type == MemoryType.EPISODIC
        assert record.content["event_type"] == "agent_decision"
        assert storage.store_count == 1

    def test_confidence_out_of_range_rejected(self):
        engine, _, _ = make_engine()
        with pytest.raises(ValueError, match="confidence"):
            engine.capture_agent_decision(
                decision_type="test", input_summary="test",
                output_action="test", confidence=1.5,
                agent_id="agent-test", operation_id="op-009",
            )


class TestSubscriberRouting:
    def test_detect_execution_outcome(self):
        assert MemoryEventSubscriber._detect_event_type({"order_id": "x"}) == "execution_outcome"

    def test_detect_risk_assessment(self):
        assert MemoryEventSubscriber._detect_event_type({"assessment_type": "x"}) == "risk_assessment"

    def test_detect_agent_decision(self):
        assert MemoryEventSubscriber._detect_event_type({"decision_type": "x"}) == "agent_decision"

    def test_detect_unknown(self):
        assert MemoryEventSubscriber._detect_event_type({"random": "x"}) == "unknown"
