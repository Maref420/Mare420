"""E2E Cross-Language Memory Pipeline Integration Test.

Verifies the complete data flow:
  Rust serialization format → Go envelope validation → Python ExperienceEngine → Storage

Uses compiled Go binary (/tmp/envelope_validate) for real cross-language validation.
Binary built from: services/message_broker/cmd/validate/main.go

Governed by:
- contracts/schemas/memory/memory-experience-event-v1.json
- Architecture Review: ARCH-REVIEW-002
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from intelligence.agent_control_plane.audit.memory_sink import InMemoryAuditSink
from intelligence.agent_control_plane.audit.models import AuditResult
from intelligence.memory_system.experience_engine.engine import ExperienceEngine
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import MemoryType
from intelligence.memory_system.retrieval_engine.engine import MemoryRetrievalEngine
from intelligence.memory_system.storage.interface import MemoryStorage

VALIDATE_BINARY = Path("/tmp/envelope_validate")


class InMemoryStorage(MemoryStorage):
    def __init__(self) -> None:
        self.records: dict[str, Any] = {}

    def store(self, record):
        self.records[record.memory_id] = record

    def retrieve(self, memory_id):
        return self.records.get(memory_id)

    def delete(self, memory_id):
        return self.records.pop(memory_id, None) is not None


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "schemas" / "memory" / "memory-experience-event-v1.json"


def load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def make_rust_style_envelope(payload: dict) -> bytes:
    """Produce an EngineMessage envelope matching Rust memory_events.rs output."""
    msg = {
        "contract_version": "1.0",
        "message_type": "memory.experience.v1",
        "source_engine": "rust_engine",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
        "metadata": {
            "specification_id": "memory-experience-event-v1",
            "policy_version": "1.0",
            "owner": "Contract Layer",
            "validation_status": "validated",
        },
    }
    return json.dumps(msg).encode("utf-8")


def go_validate_envelope(data: bytes) -> bool:
    """Validate envelope using compiled Go binary (real production code path)."""
    if not VALIDATE_BINARY.exists():
        raise RuntimeError(
            f"Go validation binary not found at {VALIDATE_BINARY}. "
            "Build with: cd services/message_broker && "
            "go build -o /tmp/envelope_validate ./cmd/validate/"
        )
    result = subprocess.run(
        [str(VALIDATE_BINARY)],
        input=data,
        capture_output=True,
        timeout=5,
    )
    return result.returncode == 0


class TestCrossLanguageMemoryPipeline:
    """Verify Rust→Go→Python data flow for memory experience events."""

    def test_execution_outcome_full_pipeline(self):
        """Execution outcome: Rust format → Go validation → Python storage + audit."""
        payload = {
            "order_id": "ord-e2e-001",
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": 2.5,
            "pnl": -300.0,
            "status": "filled",
        }
        envelope_data = make_rust_style_envelope(payload)

        # Step 1: Go validates the envelope
        assert go_validate_envelope(envelope_data), \
            "Go envelope.Validate() rejected valid execution_outcome"

        # Step 2: Python consumes and stores
        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        audit = InMemoryAuditSink()
        engine = ExperienceEngine(kernel, audit)

        parsed = json.loads(envelope_data)
        p = parsed["payload"]
        record = engine.capture_execution_outcome(
            order_id=p["order_id"],
            symbol=p["symbol"],
            side=p["side"],
            quantity=p["quantity"],
            pnl=p["pnl"],
            status=p["status"],
            agent_id="agent-e2e",
            operation_id="op-e2e-001",
        )

        # Step 3: Verify storage
        assert record.memory_type == MemoryType.EPISODIC
        assert len(storage.records) == 1

        # Step 4: Verify retrieval
        retrieval = MemoryRetrievalEngine(storage)
        retrieved = retrieval.retrieve(record.memory_id)
        assert retrieved is not None
        assert retrieved.content["order_id"] == "ord-e2e-001"

        # Step 5: Verify audit trail
        events = audit.events()
        assert len(events) == 1
        assert events[0].result == AuditResult.SUCCESS
        assert events[0].metadata["source"] == "experience_engine"

    def test_risk_assessment_full_pipeline(self):
        """Risk assessment: Rust format → Go validation → Python storage."""
        payload = {
            "assessment_type": "exposure_check",
            "result": "warn",
            "circuit_breaker_state": "normal",
            "risk_score": 75.0,
        }
        envelope_data = make_rust_style_envelope(payload)

        assert go_validate_envelope(envelope_data), \
            "Go envelope.Validate() rejected valid risk_assessment"

        storage = InMemoryStorage()
        kernel = MemoryKernel(storage)
        audit = InMemoryAuditSink()
        engine = ExperienceEngine(kernel, audit)

        parsed = json.loads(envelope_data)
        p = parsed["payload"]
        record = engine.capture_risk_assessment(
            assessment_type=p["assessment_type"],
            result=p["result"],
            circuit_breaker_state=p["circuit_breaker_state"],
            risk_score=p["risk_score"],
            agent_id="agent-e2e",
            operation_id="op-e2e-002",
        )

        assert record.memory_type == MemoryType.EPISODIC
        assert len(storage.records) == 1
        assert audit.events()[0].result == AuditResult.SUCCESS

    def test_invalid_payload_rejected_by_go(self):
        """Invalid memory event must be rejected by Go envelope validator."""
        invalid_payload = {"unknown_field": "should_fail"}
        envelope_data = make_rust_style_envelope(invalid_payload)

        assert not go_validate_envelope(envelope_data), \
            "Go should reject unknown memory event type"

    def test_schema_contract_exists_and_valid(self):
        """Verify the governing schema file exists and is valid JSON."""
        assert SCHEMA_PATH.exists(), f"Schema not found at {SCHEMA_PATH}"
        schema = load_schema()
        assert schema["version"] == "1.0"
        assert "execution_outcome" in schema["event_types"]
        assert "risk_assessment" in schema["event_types"]
        assert "agent_decision" in schema["event_types"]
        assert schema["rules"]["transport_must_use_broker"] is True
