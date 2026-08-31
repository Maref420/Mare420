"""Tests for strategy signal audit logger.

Verifies audit records are created correctly for both accepted
and rejected strategy signals using the legacy boundary format.

Governed by:
- contracts/schemas/audit/audit-storage-v1.json
- governance/policies/python-policy.yaml
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from intelligence.strategy_intelligence.contract_adapter import (
    ContractValidationError,
    StrategySignalEventV1,
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
        "confidence": 0.75,
        "regime": "TRENDING",
    },
})


@patch("intelligence.strategy_intelligence.strategy_audit_logger._get_sink")
def test_log_received_success(mock_sink_factory):
    mock_sink = MagicMock()
    mock_sink_factory.return_value = mock_sink

    event = StrategySignalEventV1.from_json(SAMPLE_JSON)
    log_strategy_signal_received(SAMPLE_JSON, event, operation_id="op-001")

    mock_sink.record.assert_called_once()
    record = mock_sink.record.call_args[0][0]
    assert record.event_id == "550e8400-e29b-41d4-a716-446655440000"
    assert record.agent_id == "test_agent"
    assert record.metadata["symbol"] == "BTCUSDT"
    assert record.metadata["direction"] == "LONG"


@patch("intelligence.strategy_intelligence.strategy_audit_logger._get_sink")
def test_log_received_with_trace_id(mock_sink_factory):
    mock_sink = MagicMock()
    mock_sink_factory.return_value = mock_sink

    data = json.loads(SAMPLE_JSON)
    data["trace_id"] = "660e8400-e29b-41d4-a716-446655440001"
    raw = json.dumps(data)
    event = StrategySignalEventV1.from_json(raw)
    log_strategy_signal_received(raw, event)

    mock_sink.record.assert_called_once()


@patch("intelligence.strategy_intelligence.strategy_audit_logger._get_sink")
def test_log_rejected_records_failure(mock_sink_factory):
    mock_sink = MagicMock()
    mock_sink_factory.return_value = mock_sink

    log_strategy_signal_rejected(
        raw_json='{"invalid": true}',
        error="unknown fields: {'invalid'}",
        source_agent="bad_agent",
        operation_id="op-002",
    )

    mock_sink.record.assert_called_once()
    record = mock_sink.record.call_args[0][0]
    assert record.agent_id == "bad_agent"
    assert record.metadata["rejection_reason"] == "unknown fields: {'invalid'}"


@patch("intelligence.strategy_intelligence.strategy_audit_logger._get_sink")
def test_log_rejected_malformed_json(mock_sink_factory):
    mock_sink = MagicMock()
    mock_sink_factory.return_value = mock_sink

    log_strategy_signal_rejected(
        raw_json="not json at all",
        error="invalid JSON",
        source_agent="unknown",
    )

    mock_sink.record.assert_called_once()
    record = mock_sink.record.call_args[0][0]
    assert record.event_id == "unknown"
