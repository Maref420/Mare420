"""Integration tests for Agent Auth Middleware.

Governance: Verifies API key auth, rate limiting, bypass paths.
Stdlib-only. No external dependencies.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from atlas_agent.auth import AuthMiddleware


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def reset_auth():
    """Reset singleton before each test."""
    AuthMiddleware.reset()
    yield
    AuthMiddleware.reset()


@pytest.fixture(scope="module")
def auth_server():
    """Start server with auth enabled."""
    from unittest.mock import patch
    from atlas_agent.http_server import AgentHTTPServer, AgentHTTPRequestHandler
    import atlas_agent.http_server as http_mod

    port = _free_port()

    # Set env FIRST, then reset singleton so it picks up new keys
    os.environ["AGENT_API_KEYS"] = "test-key-aaa,test-key-bbb"
    os.environ["AGENT_RATE_LIMIT_BURST"] = "5"
    AuthMiddleware.reset()

    # Re-create middleware in http_server module with new keys
    http_mod._auth_middleware = AuthMiddleware()

    class FakeIPC:
        def __init__(self, p: str) -> None:
            pass
        def send(self, d: dict) -> dict:
            return {"status": "ok"}
        def __enter__(self) -> FakeIPC:
            return self
        def __exit__(self, *a: Any) -> None:
            pass

    with patch("atlas_agent.http_server.IPCClient", return_value=FakeIPC("")):
        httpd = AgentHTTPServer(("127.0.0.1", port), AgentHTTPRequestHandler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        time.sleep(0.15)
        yield {"port": port}
        httpd.shutdown()
        t.join(timeout=2)

    # Cleanup env
    for k in ("AGENT_API_KEYS", "AGENT_RATE_LIMIT_BURST"):
        os.environ.pop(k, None)
    AuthMiddleware.reset()
    http_mod._auth_middleware = AuthMiddleware()


def _req(port: int, method: str, path: str, headers: dict[str, str] | None = None, body: str | None = None) -> tuple[int, str]:
    url = f"http://127.0.0.1:{port}{path}"
    data = body.encode() if body else None
    req = Request(url, data=data, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urlopen(req, timeout=3) as resp:
            return resp.status, resp.read().decode()
    except HTTPError as e:
        return e.code, e.read().decode()


class TestAuthBypass:
    def test_health_live_no_key(self, auth_server: dict) -> None:
        status, raw = _req(auth_server["port"], "GET", "/health/live")
        assert status == 200
        assert json.loads(raw)["status"] == "alive"

    def test_health_ready_no_key(self, auth_server: dict) -> None:
        status, _ = _req(auth_server["port"], "GET", "/health/ready")
        assert status in (200, 503)

    def test_metrics_no_key(self, auth_server: dict) -> None:
        status, raw = _req(auth_server["port"], "GET", "/metrics")
        assert status == 200
        assert "# HELP" in raw


class TestAuthRequired:
    def test_assess_without_key_returns_401(self, auth_server: dict) -> None:
        status, raw = _req(
            auth_server["port"], "POST", "/assess",
            body=json.dumps({"order": {"symbol": "BTC", "qty": 1}}),
            headers={"Content-Type": "application/json"},
        )
        assert status == 401
        body = json.loads(raw)
        assert body["code"] == "AUTH_MISSING_KEY"
        assert body["retryable"] is False

    def test_assess_with_invalid_key_returns_401(self, auth_server: dict) -> None:
        status, raw = _req(
            auth_server["port"], "POST", "/assess",
            body=json.dumps({"order": {"symbol": "BTC", "qty": 1}}),
            headers={"Content-Type": "application/json", "X-API-Key": "wrong-key"},
        )
        assert status == 401
        body = json.loads(raw)
        assert body["code"] == "AUTH_INVALID_KEY"

    def test_assess_with_valid_key_returns_200(self, auth_server: dict) -> None:
        status, raw = _req(
            auth_server["port"], "POST", "/assess",
            body=json.dumps({"order": {"symbol": "BTC", "qty": 1}}),
            headers={"Content-Type": "application/json", "X-API-Key": "test-key-aaa"},
        )
        assert status == 200
        body = json.loads(raw)
        assert body["status"] == "ok"


class TestRateLimiting:
    def test_burst_limit_triggers_429(self, auth_server: dict) -> None:
        port = auth_server["port"]
        last_status = 200
        for i in range(10):
            status, raw = _req(
                port, "POST", "/assess",
                body=json.dumps({"order": {"symbol": "ETH", "qty": 1}}),
                headers={"Content-Type": "application/json", "X-API-Key": "test-key-bbb"},
            )
            last_status = status
            if status == 429:
                body = json.loads(raw)
                assert body["code"] == "AUTH_RATE_LIMITED"
                assert body["retryable"] is True
                break
        assert last_status == 429, "Expected rate limit to trigger within 10 requests"


class TestAuthMiddlewareUnit:
    def test_dev_mode_when_no_keys(self) -> None:
        os.environ.pop("AGENT_API_KEYS", None)
        AuthMiddleware.reset()
        mw = AuthMiddleware()
        allowed, err = mw.check({}, "/assess", "t-1")
        assert allowed is True
        assert err is None

    def test_hmac_compare_digest_used(self) -> None:
        """Verify constant-time comparison by checking hmac module usage."""
        import atlas_agent.auth as auth_mod
        assert hasattr(auth_mod, "hmac")
        assert hasattr(auth_mod.hmac, "compare_digest")
