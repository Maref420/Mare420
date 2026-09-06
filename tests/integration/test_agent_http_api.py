"""Integration tests for Agent HTTP Server.

Governance: Verifies health, assess, metrics, error envelope, trace_id.
Uses unittest.mock for IPC — no real socket required.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError

import pytest

from atlas_agent.http_server import (
    AgentHTTPServer,
    AgentHTTPRequestHandler,
    create_error_envelope,
)


class _MockIPCClient:
    """Mock IPC client for testing without real socket."""

    def __init__(self, socket_path: str) -> None:
        self.socket_path = socket_path
        self.call_count = 0
        self.last_payload: dict[str, Any] = {}

    def send(self, data: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        self.last_payload = data
        return {"status": "processed", "engine_response": "mocked"}

    def __enter__(self) -> _MockIPCClient:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


@pytest.fixture(scope="module")
def server():
    """Start test HTTP server with mocked IPC."""
    from unittest.mock import patch

    mock_ipc = _MockIPCClient("/tmp/test-ipc.sock")
    with patch("atlas_agent.http_server.IPCClient", return_value=mock_ipc):
        httpd = AgentHTTPServer(("127.0.0.1", 0), AgentHTTPRequestHandler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.1)
        yield {"port": port, "mock_ipc": mock_ipc}
        httpd.shutdown()
        thread.join(timeout=2)


def _request(port: int, method: str, path: str, data: Any = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any], dict[str, str]]:
    url = f"http://127.0.0.1:{port}{path}"
    payload = json.dumps(data).encode() if data else None
    req = Request(url, data=payload, method=method)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read().decode())
            resp_headers = {k: resp.headers[k] for k in resp.headers}
            return resp.status, body, resp_headers
    except URLError as e:
        if hasattr(e, "read"):
            body = json.loads(e.read().decode())
            resp_headers = {k: e.headers[k] for k in e.headers} if e.headers else {}
            code = e.code if hasattr(e, "code") else 500
            return code, body, resp_headers
        raise


class TestHealthEndpoints:
    def test_live_returns_200(self, server: dict) -> None:
        status, body, _ = _request(server["port"], "GET", "/health/live")
        assert status == 200
        assert body["status"] == "alive"

    def test_ready_returns_200_when_deps_exist(self, server: dict, tmp_path: Any) -> None:
        import os
        from unittest.mock import patch
        with patch("os.path.exists", return_value=True), \
             patch("os.path.isdir", return_value=True), \
             patch("os.path.isfile", return_value=True):
            status, body, _ = _request(server["port"], "GET", "/health/ready")
        assert status == 200
        assert body["status"] == "ready"


class TestAssessEndpoint:
    def test_valid_assess_returns_success(self, server: dict) -> None:
        payload = {"order": {"symbol": "BTCUSDT", "qty": 1.0, "side": "buy"}}
        status, body, _ = _request(server["port"], "POST", "/assess", data=payload)
        assert status == 200
        assert body["status"] == "processed"
        assert server["mock_ipc"].call_count >= 1

    def test_invalid_json_returns_error_envelope(self, server: dict) -> None:
        url = f"http://127.0.0.1:{server['port']}/assess"
        req = Request(url, data=b"not-json", method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            urlopen(req, timeout=3)
            pytest.fail("Expected URLError")
        except URLError as e:
            body = json.loads(e.read().decode())
            assert "code" in body
            assert body["code"] == "VAL_INVALID_INPUT"
            assert "trace_id" in body

    def test_missing_order_returns_error_envelope(self, server: dict) -> None:
        status, body, _ = _request(server["port"], "POST", "/assess", data={"foo": "bar"})
        assert status == 400
        assert body["code"] == "VAL_MISSING_ORDER"
        assert body["retryable"] is False


class TestMetricsEndpoint:
    def test_metrics_returns_prometheus_format(self, server: dict) -> None:
        url = f"http://127.0.0.1:{server['port']}/metrics"
        req = Request(url, method="GET")
        with urlopen(req, timeout=3) as resp:
            text = resp.read().decode()
        assert "# HELP agent_http_requests_total" in text
        assert "# TYPE agent_http_requests_total counter" in text


class TestTraceId:
    def test_trace_id_injected_in_response(self, server: dict) -> None:
        _, _, headers = _request(server["port"], "GET", "/health/live")
        assert "X-Trace-Id" in headers or "x-trace-id" in headers

    def test_custom_trace_id_propagated(self, server: dict) -> None:
        custom_id = str(uuid.uuid4())
        _, _, headers = _request(
            server["port"], "GET", "/health/live",
            headers={"X-Trace-Id": custom_id},
        )
        returned = headers.get("X-Trace-Id") or headers.get("x-trace-id")
        assert returned == custom_id


class TestErrorEnvelope:
    def test_envelope_structure(self) -> None:
        env = create_error_envelope("VAL_TEST", "test msg", retryable=False, trace_id="t-1")
        assert env["code"] == "VAL_TEST"
        assert env["message"] == "test msg"
        assert env["retryable"] is False
        assert env["trace_id"] == "t-1"
        assert "timestamp_ms" in env
        assert "cause_chain" in env

    def test_unknown_path_returns_404(self, server: dict) -> None:
        status, body, _ = _request(server["port"], "GET", "/nonexistent")
        assert status == 404
        assert body["code"] == "VAL_INVALID_PATH"
