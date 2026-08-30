"""Tests for strategy_audit_logger module.

Verifies audit records are correctly constructed for accepted and rejected signals.
Uses MemorySink to avoid Supabase dependency in tests.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from intelligence.agent_control_plane.audit.models import (
    AuditEventType,
    AuditAction,
    AuditResult,
)
from intelligence.strategy_intelligence.contract_adapter import (
    StrategySignalEventV1,
    ContractValidationError,
)
from intelligence.strategy_intelligence.strategy_audit_logger import (
    log_strategy_signal_received,
    log_strategy_signal_rejected,
)

SAMPLE_JSON = json.dumps({
    "version": "1.0.0",
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp_utc": "2026-08-31T10:00:00Z",
    "source_agent": "test_agent",
    "signal": {
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "confidence": 0.87,
        "regime": "TRENDING",
    },
})


class TestLogStrategySignalReceived:

    @patch("intelligence.strategy_intelligence.strategy_audit_logger._get_sink")
    def test_creates_correct_audit_record(self, mock_get_sink):
        mock_sink = MagicMock()
        mock_get_sink.return_value = mock_sink

        event = StrategySignalEventV1.from_json(SAMPLE_JSON)
        log_strategy_signal_received(SAMPLE_JSON, event, operation_id="op-test-001")

        mock_sink.record.assert_called_once()
        record = mock_sink.record.call_args[0][0]

        assert record.event_type == AuditEventType.STRATEGY_SIGNAL_RECEIVED
        assert record.event_id == "550e8400-e29b-41d4-a716-446655440000"
        assert record.agent_id == "test_agent"
        assert record.action == AuditAction.COMPLETED
        assert record.result == AuditResult.SUCCESS
        assert record.resource == "strategy_signal:550e8400-e29b-41d4-a716-446655440000"
        assert record.metadata["symbol"] == "BTCUSDT"
        assert record.metadata["direction"] == "LONG"
        assert record.operation_id == "op-test-001"

    @patch("intelligence.strategy_intelligence.strategy_audit_logger._get_sink")
    def test_auto_generates_operation_id(self, mock_get_sink):
        mock_sink = MagicMock()
        mock_get_sink.return_value = mock_sink

        event = StrategySignalEventV1.from_json(SAMPLE_JSON)
        log_strategy_signal_received(SAMPLE_JSON, event)

        record = mock_sink.record.call_args[0][0]
        assert len(record.operation_id) > 0  # UUID generated

    @patch("intelligence.strategy_intelligence.strategy_audit_logger._get_sink")
    def test_never_raises_on_sink_failure(self, mock_get_sink):
        mock_sink = MagicMock()
        mock_sink.record.side_effect = RuntimeError("DB down")
        mock_get_sink.return_value = mock_sink

        event = StrategySignalEventV1.from_json(SAMPLE_JSON)
        # Should NOT raise
        log_strategy_signal_received(SAMPLE_JSON, event)


class TestLogStrategySignalRejected:

    @patch("intelligence.strategy_intelligence.strategy_audit_logger._get_sink")
    def test_logs_rejected_signal(self, mock_get_sink):
        mock_sink = MagicMock()
        mock_get_sink.return_value = mock_sink

        log_strategy_signal_rejected(
            raw_json=SAMPLE_JSON,
            error="symbol x does not match pattern",
            source_agent="bad_agent",
        )

        mock_sink.record.assert_called_once()
        record = mock_sink.record.call_args[0][0]

        assert record.event_type == AuditEventType.STRATEGY_SIGNAL_RECEIVED
        assert record.action == AuditAction.FAILED
        assert record.result == AuditResult.FAILURE
        assert record.agent_id == "bad_agent"
        assert "rejection_reason" in record.metadata

    @patch("intelligence.strategy_intelligence.strategy_audit_logger._get_sink")
    def test_handles_unparseable_json(self, mock_get_sink):
        mock_sink = MagicMock()
        mock_get_sink.return_value = mock_sink

        log_strategy_signal_rejected(
            raw_json="not valid json{{{",
            error="invalid JSON",
        )

        record = mock_sink.record.call_args[0][0]
        assert record.event_id == "unknown"
        assert record.agent_id == "unknown"

    @patch("intelligence.strategy_intelligence.strategy_audit_logger._get_sink")
    def test_never_raises_on_sink_failure(self, mock_get_sink):
        mock_sink = MagicMock()
        mock_sink.record.side_effect = RuntimeError("DB down")
        mock_get_sink.return_value = mock_sink

        # Should NOT raise
        log_strategy_signal_rejected(SAMPLE_JSON, "some error")
