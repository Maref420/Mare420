"""Integration test: IPC server wired to real risk engine.

Data Flow:
1. Start Rust IPC server (wired to assess_order) as subprocess
2. Python IPCClient sends risk assessment request
3. Server calls atlas_risk_engine::assess_order() 
4. Returns RiskAssessment with approved/rejected status
5. Verify real risk logic executed (not echo)

Governance: Transport AI-generated (§17 compliant). Wiring manual.
"""
from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
import uuid

import pytest

from atlas_agent.engine_ipc_client import IPCClient


@pytest.fixture
def ipc_socket_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".sock")
    os.close(fd)
    os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def risk_ipc_server(ipc_socket_path: str) -> subprocess.Popen:
    binary = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "core_engine", "ipc_server", "target", "debug", "atlas-ipc-server"
    )
    if not os.path.exists(binary):
        pytest.skip("IPC server binary not built")

    env = os.environ.copy()
    env["IPC_SOCKET_PATH"] = ipc_socket_path
    env["RUST_LOG"] = "info"

    proc = subprocess.Popen([binary], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for _ in range(50):
        if os.path.exists(ipc_socket_path):
            break
        time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("IPC server did not start within 5s")

    yield proc
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


class TestIPCRiskWired:
    def test_approved_order(self, risk_ipc_server: subprocess.Popen, ipc_socket_path: str) -> None:
        """Valid order within limits should be approved."""
        request = {
            "order_id": str(uuid.uuid4()),
            "agent_id": "test-agent-001",
            "symbol": "BTC-USDT",
            "quantity": 0.5,
            "max_order_quantity": 10.0,
            "allowed_symbols": ["BTC-USDT", "ETH-USDT"],
            "require_risk_score": True,
        }
        with IPCClient(ipc_socket_path) as client:
            response = client.send(request)

        assert response["success"] is True
        assert response["assessment"]["approved"] is True
        assert response["assessment"]["agent_id"] == "test-agent-001"
        assert "symbol_check" in response["assessment"]["checks_performed"]
        assert "quantity_check" in response["assessment"]["checks_performed"]
        assert response["assessment"]["risk_score"] == 0.5

    def test_rejected_over_quantity(
        self, risk_ipc_server: subprocess.Popen, ipc_socket_path: str
    ) -> None:
        """Order exceeding max quantity should be rejected."""
        request = {
            "order_id": str(uuid.uuid4()),
            "agent_id": "test-agent-002",
            "symbol": "BTC-USDT",
            "quantity": 999.0,
            "max_order_quantity": 10.0,
            "allowed_symbols": [],
        }
        with IPCClient(ipc_socket_path) as client:
            response = client.send(request)

        assert response["success"] is True
        assert response["assessment"]["approved"] is False
        assert "exceeds max" in response["assessment"]["rejection_reason"]

    def test_rejected_disallowed_symbol(
        self, risk_ipc_server: subprocess.Popen, ipc_socket_path: str
    ) -> None:
        """Order with symbol not in allowed list should be rejected."""
        request = {
            "order_id": str(uuid.uuid4()),
            "agent_id": "test-agent-003",
            "symbol": "DOGE-USDT",
            "quantity": 1.0,
            "max_order_quantity": 100.0,
            "allowed_symbols": ["BTC-USDT", "ETH-USDT"],
        }
        with IPCClient(ipc_socket_path) as client:
            response = client.send(request)

        assert response["success"] is True
        assert response["assessment"]["approved"] is False
        assert "not in allowed list" in response["assessment"]["rejection_reason"]

    def test_invalid_order_id_returns_error(
        self, risk_ipc_server: subprocess.Popen, ipc_socket_path: str
    ) -> None:
        """Invalid UUID in order_id should return error response."""
        request = {
            "order_id": "not-a-valid-uuid",
            "agent_id": "test-agent",
            "symbol": "BTC-USDT",
            "quantity": 1.0,
        }
        with IPCClient(ipc_socket_path) as client:
            response = client.send(request)

        assert response["success"] is False
        assert "invalid order_id" in response["error"]

    def test_non_risk_request_gets_echo(
        self, risk_ipc_server: subprocess.Popen, ipc_socket_path: str
    ) -> None:
        """Non-risk JSON still gets processed (graceful fallback)."""
        request = {"hello": "world", "type": "ping"}
        with IPCClient(ipc_socket_path) as client:
            response = client.send(request)

        # Should get echo fallback since it's not a valid RiskRequest
        assert response.get("status") == "ok" or response.get("success") is not None
