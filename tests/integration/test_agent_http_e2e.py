"""E2E integration tests for Agent HTTP Server.

OG-generated, competitor-reviewed, manually corrected.
Tests use real HTTP requests against a live test server.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid
import urllib.request
import urllib.error
from unittest.mock import MagicMock, patch
from typing import Any

import pytest

from atlas_agent.http_server import (
    AgentHTTPServer,
    AgentHTTPRequestHandler,
    create_error_envelope,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _FakeIPC:
    """Fake IPC client — returns dict directly, no Future."""

    def __init__(self, socket_path: str) -> None:
        self.socket_path = socket_path
        self.call_count = 0
        self.last_payload: dict[str, Any] = {}

    def send(self, data: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        self.last_payload = data
        return {"status": "approved", "score": 0.95, "req_id": "engine-mock-1"}

    def __enter__(self) -> _FakeIPC:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


@pytest.fixture(scope="module")
def live_server():
    """Start real HTTP server with mocked IPC on random port."""
    port = _free_port()
    fake_ipc = _FakeIPC("/tmp/test-ipc.sock")

    with patch("atlas_agent.http_server.IPCClient", return_value=fake_ipc):
        httpd = AgentHTTPServer(("127.0.0.1", port), AgentHTTPRequestHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.15)
        yield {"port": port, "ipc": fake_ipc}
        httpd.shutdown()
        thread.join(timeout=2)


def _req(
    port: int,
    method: str,
    path: str,
    body: str | bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str, dict[str, str]]:
    """Make real HTTP request. Returns (status, raw_body, headers)."""
    url = f"http://127.0.0.1:{port}{path}"
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            raw = resp.read().decode("utf-8")
            resp_headers = {k: resp.headers[k] for k in resp.headers}
            return resp.status, raw, resp_headers
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        resp_headers = {k: e.headers[k] for k in e.headers} if e.headers else {}
        return e.code, raw, resp_headers


# ===================================================================
# Health Endpoints
# ===================================================================

class TestHealthLive:
    def test_returns_200_alive(self, live_server: dict) -> None:
        status, raw, _ = _req(live_server["port"], "GET", "/health/live")
        assert status == 200
        body = json.loads(raw)
        assert body["status"] == "alive"

    def test_trace_id_in_header(self, live_server: dict) -> None:
        _, _, headers = _req(live_server["port"], "GET", "/health/live")
        trace = headers.get("X-Trace-Id") or headers.get("x-trace-id")
        assert trace is not None
        uuid.UUID(trace)  # valid UUID format


class TestHealthReady:
    def test_returns_200_or_503(self, live_server: dict) -> None:
        status, raw, _ = _req(live_server["port"], "GET", "/health/ready")
        body = json.loads(raw)
        if status == 200:
            assert body["status"] == "ready"
        else:
            assert status == 503
            assert body["code"] == "DEP_NOT_READY"
            assert body["retryable"] is True


# ===================================================================
# Assess Endpoint
# ===================================================================

class TestAssess:
    def test_valid_order_returns_200(self, live_server: dict) -> None:
        payload = json.dumps({"order": {"symbol": "BTCUSDT", "qty": 1.0, "side": "buy"}})
        status, raw, _ = _req(
            live_server["port"], "POST", "/assess",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        assert status == 200
        body = json.loads(raw)
        assert body["status"] == "approved"
        assert live_server["ipc"].call_count >= 1

    def test_invalid_json_returns_400(self, live_server: dict) -> None:
        status, raw, _ = _req(
            live_server["port"], "POST", "/assess",
            body="{bad json!!!",
            headers={"Content-Type": "application/json"},
        )
        assert status == 400
        body = json.loads(raw)
        assert body["code"] == "VAL_INVALID_INPUT"

    def test_missing_order_returns_400(self, live_server: dict) -> None:
        status, raw, _ = _req(
            live_server["port"], "POST", "/assess",
            body=json.dumps({"foo": "bar"}),
            headers={"Content-Type": "application/json"},
        )
        assert status == 400
        body = json.loads(raw)
        assert body["code"] == "VAL_MISSING_ORDER"
        assert body["retryable"] is False

    def test_trace_id_propagated(self, live_server: dict) -> None:
        custom_id = str(uuid.uuid4())
        _, _, headers = _req(
            live_server["port"], "POST", "/assess",
            body=json.dumps({"order": {"symbol": "ETHUSDT", "qty": 5}}),
            headers={"Content-Type": "application/json", "X-Trace-Id": custom_id},
        )
        returned = headers.get("X-Trace-Id") or headers.get("x-trace-id")
        assert returned == custom_id


# ===================================================================
# Metrics Endpoint
# ===================================================================

class TestMetrics:
    def test_returns_prometheus_text(self, live_server: dict) -> None:
        status, raw, headers = _req(live_server["port"], "GET", "/metrics")
        assert status == 200
        assert "text/plain" in (headers.get("Content-Type") or headers.get("content-type", ""))
        assert "# HELP agent_http_requests_total" in raw
        assert "# TYPE agent_http_requests_total counter" in raw

    def test_histogram_present(self, live_server: dict) -> None:
        _, raw, _ = _req(live_server["port"], "GET", "/metrics")
        assert "agent_http_request_duration_seconds" in raw


# ===================================================================
# Error Handling
# ===================================================================

class TestErrorHandling:
    def test_404_on_unknown_path(self, live_server: dict) -> None:
        status, raw, _ = _req(live_server["port"], "GET", "/nonexistent")
        assert status == 404
        body = json.loads(raw)
        assert body["code"] == "VAL_INVALID_PATH"

    def test_error_envelope_structure(self, live_server: dict) -> None:
        status, raw, _ = _req(live_server["port"], "GET", "/nonexistent")
        body = json.loads(raw)
        assert "trace_id" in body
        assert "service" in body
        assert "code" in body
        assert "retryable" in body
        assert "message" in body
        assert "timestamp_ms" in body
        assert isinstance(body["retryable"], bool)

    def test_custom_trace_id_in_error(self, live_server: dict) -> None:
        custom = "my-custom-trace-42"
        status, raw, headers = _req(
            live_server["port"], "GET", "/nonexistent",
            headers={"X-Trace-Id": custom},
        )
        body = json.loads(raw)
        returned_header = headers.get("X-Trace-Id") or headers.get("x-trace-id")
        assert returned_header == custom


# ===================================================================
# ErrorEnvelope Unit Test
# ===================================================================

class TestCreateErrorEnvelope:
    def test_structure(self) -> None:
        env = create_error_envelope("TEST_CODE", "test msg", retryable=True, trace_id="t-1")
        assert env["code"] == "TEST_CODE"
        assert env["message"] == "test msg"
        assert env["retryable"] is True
        assert env["trace_id"] == "t-1"
        assert "timestamp_ms" in env
        assert "cause_chain" in env

    def test_auto_generates_trace_id(self) -> None:
        env = create_error_envelope("X", "y")
        assert len(env["trace_id"]) > 0
        uuid.UUID(env["trace_id"])
