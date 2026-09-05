"""Integration test: cross-language ErrorEnvelope contract compliance.

DATA FLOW:
1. Python Agent creates ErrorEnvelope via foundation.error factories
2. Serializes to JSON via to_json()
3. Go Gateway would parse this JSON and route based on code + retryable
4. trace_id propagates from edge (gateway) through agent to engine

Architecture: Gateway(Go) -> Agent(Python) -> Engine(Rust)
Contract: governance/schemas/engine-contract-v1.json
Governance: CONSTITUTION v1.2, Sections 3/6/7 compliance verified.

This test proves the Python ErrorEnvelope produces JSON that a Go gateway
can parse and make routing decisions on (retry vs fail-fast).
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from foundation.error import (
    ErrorEnvelope,
    val_error,
    auth_error,
    biz_error,
    dep_error,
    res_error,
    net_error,
    int_error,
    should_retry,
)
from foundation.logger import set_trace_id, get_trace_id

REQUIRED_SCHEMA_KEYS: list[str] = [
    "trace_id",
    "span_id",
    "service",
    "code",
    "retryable",
    "http_status",
    "message",
    "details",
    "cause_chain",
    "timestamp_ms",
]


class TestSchemaCompliance:
    """Verify ErrorEnvelope JSON matches engine contract schema."""

    def test_serialization_contains_all_required_fields(self) -> None:
        envelope = val_error("INVALID_INPUT", "test payload", service="agent")
        payload: dict[str, Any] = json.loads(envelope.to_json())
        assert set(payload.keys()) == set(REQUIRED_SCHEMA_KEYS), (
            f"Schema mismatch. Got {sorted(payload.keys())}"
        )

    def test_field_types_match_contract(self) -> None:
        envelope = dep_error("UPSTREAM_TIMEOUT", "db timeout", service="engine")
        payload: dict[str, Any] = json.loads(envelope.to_json())
        assert isinstance(payload["trace_id"], str)
        assert isinstance(payload["span_id"], str)
        assert isinstance(payload["service"], str)
        assert isinstance(payload["code"], str)
        assert isinstance(payload["retryable"], bool)
        assert isinstance(payload["http_status"], int)
        assert isinstance(payload["message"], str)
        assert isinstance(payload["timestamp_ms"], int)
        assert payload["details"] is None or isinstance(payload["details"], dict)
        assert payload["cause_chain"] is None or isinstance(payload["cause_chain"], list)


class TestCodeFamilies:
    """Each code family must produce correct HTTP status and retryable."""

    def test_val_family_no_retry_http_400(self) -> None:
        e = val_error("INVALID_INPUT", "bad input", service="gateway")
        assert e.retryable is False
        assert e.http_status == 400
        assert e.code.startswith("VAL_")
        assert should_retry(e) is False

    def test_auth_family_no_retry_http_401(self) -> None:
        e = auth_error("TOKEN_EXPIRED", "invalid token", service="gateway")
        assert e.retryable is False
        assert e.http_status == 401
        assert e.code.startswith("AUTH_")
        assert should_retry(e) is False

    def test_biz_family_no_retry_http_422(self) -> None:
        e = biz_error("RULE_VIOLATION", "policy violated", service="agent")
        assert e.retryable is False
        assert e.http_status == 422
        assert e.code.startswith("BIZ_")
        assert should_retry(e) is False

    def test_dep_family_retryable_http_503(self) -> None:
        e = dep_error("DB_TIMEOUT", "connection pool exhausted", service="agent")
        assert e.retryable is True
        assert e.http_status == 503
        assert e.code.startswith("DEP_")
        assert should_retry(e) is True

    def test_res_family_retryable_http_429(self) -> None:
        e = res_error("RATE_LIMITED", "too many requests", service="gateway")
        assert e.retryable is True
        assert e.http_status == 429
        assert e.code.startswith("RES_")
        assert should_retry(e) is True

    def test_net_family_retryable_http_504(self) -> None:
        e = net_error("UPSTREAM_TIMEOUT", "connection reset", service="agent")
        assert e.retryable is True
        assert e.http_status == 504
        assert e.code.startswith("NET_")
        assert should_retry(e) is True

    def test_int_family_no_retry_http_500(self) -> None:
        e = int_error("INVARIANT_BROKEN", "unexpected null", service="engine")
        assert e.retryable is False
        assert e.http_status == 500
        assert e.code.startswith("INT_")
        assert should_retry(e) is False


class TestTracePropagation:
    """trace_id must flow from context into serialized envelope."""

    def test_trace_id_from_context_appears_in_envelope(self) -> None:
        test_tid = "tid-edge-to-leaf-abc123"
        set_trace_id(test_tid)
        envelope = val_error("TEST", "propagation check", service="agent")
        payload: dict[str, Any] = json.loads(envelope.to_json())
        assert payload["trace_id"] == test_tid

    def test_explicit_trace_id_overrides_context(self) -> None:
        set_trace_id("context-tid")
        envelope = val_error(
            "TEST", "explicit tid",
            service="agent",
            trace_id="explicit-tid-override",
        )
        assert envelope.trace_id == "explicit-tid-override"


class TestCauseChain:
    """Nested errors preserve service boundaries in cause_chain."""

    def test_cause_chain_preserves_boundary_metadata(self) -> None:
        child = val_error("BAD_PAYLOAD", "invalid field", service="engine")
        parent = dep_error(
            "UPSTREAM_FAILED", "engine returned error",
            service="agent",
            cause_chain=[{
                "service": child.service,
                "code": child.code,
                "message": child.message,
            }],
        )
        payload: dict[str, Any] = json.loads(parent.to_json())
        chain = payload["cause_chain"]
        assert len(chain) == 1
        assert chain[0]["service"] == "engine"
        assert chain[0]["code"] == "VAL_BAD_PAYLOAD"

    def test_empty_cause_chain_is_none(self) -> None:
        e = val_error("X", "y", service="agent")
        assert e.cause_chain is None


class TestRoundTrip:
    """Serialize -> deserialize -> all fields preserved."""

    def test_round_trip_preserves_all_fields(self) -> None:
        set_trace_id("")  # clear context from previous tests
        envelope = int_error(
            "CRITICAL_FAILURE", "kernel panic",
            service="engine",
            details={"severity": "P0", "team": "platform"},
            cause_chain=[{"service": "rust_compute", "code": "OVERFLOW"}],
        )
        json_str = envelope.to_json()
        restored = json.loads(json_str)
        assert restored["code"] == "INT_CRITICAL_FAILURE"
        assert restored["service"] == "engine"
        assert restored["retryable"] is False
        assert restored["http_status"] == 500
        assert restored["details"] == {"severity": "P0", "team": "platform"}
        assert restored["cause_chain"] == [{"service": "rust_compute", "code": "OVERFLOW"}]
        assert len(restored["trace_id"]) >= 11  # uuid hex (32) or explicit tid
        assert restored["timestamp_ms"] > 0

    def test_message_truncated_to_500_chars(self) -> None:
        long_msg = "x" * 1000
        e = val_error("LONG_MSG", long_msg, service="agent")
        assert len(e.message) <= 500


class TestGoGatewayCompatibility:
    """Verify JSON output is what a Go gateway would expect."""

    def test_json_is_valid_single_line(self) -> None:
        e = net_error("TIMEOUT", "request timed out", service="agent")
        json_str = e.to_json()
        assert "\n" not in json_str
        parsed = json.loads(json_str)
        assert parsed["code"] == "NET_TIMEOUT"

    def test_service_field_matches_governance_values(self) -> None:
        for svc in ("gateway", "agent", "engine"):
            e = val_error("TEST", "check", service=svc)
            assert e.service == svc

    def test_invalid_service_defaults_to_agent(self) -> None:
        e = val_error("TEST", "check", service="unknown_service")
        assert e.service == "agent"
