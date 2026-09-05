"""Integration test: IPC transport layer (generic, no business logic).

Data Flow:
1. Start Rust IPC server as subprocess on temp UDS
2. Python IPCClient connects and sends JSON request
3. Server echoes back {"status":"ok","received":<input>}
4. Client receives and validates response
5. Cleanup: stop server, remove socket

Governance: transport-only test, no risk/trading logic involved.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time

import pytest

from atlas_agent.engine_ipc_client import IPCClient


@pytest.fixture
def ipc_socket_path() -> str:
    """Create a temporary socket path."""
    fd, path = tempfile.mkstemp(suffix=".sock")
    os.close(fd)
    os.unlink(path)  # remove file so UDS can bind
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def ipc_server(ipc_socket_path: str) -> subprocess.Popen:
    """Start the Rust IPC server as a subprocess."""
    binary = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "core_engine", "ipc_server", "target", "debug", "atlas-ipc-server"
    )
    if not os.path.exists(binary):
        pytest.skip("IPC server binary not built — run: cd core_engine/ipc_server && cargo build")

    env = os.environ.copy()
    env["IPC_SOCKET_PATH"] = ipc_socket_path
    env["RUST_LOG"] = "info"

    proc = subprocess.Popen(
        [binary],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for socket to appear
    for _ in range(50):
        if os.path.exists(ipc_socket_path):
            break
        time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("IPC server did not create socket within 5 seconds")

    yield proc

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


class TestIPCTransport:
    def test_echo_roundtrip(self, ipc_server: subprocess.Popen, ipc_socket_path: str) -> None:
        """Send a request and verify echo response."""
        with IPCClient(ipc_socket_path) as client:
            response = client.send({"action": "test", "value": 42})
        assert response["status"] == "ok"
        assert response["received"]["action"] == "test"
        assert response["received"]["value"] == 42

    def test_multiple_requests_single_connection(
        self, ipc_server: subprocess.Popen, ipc_socket_path: str
    ) -> None:
        """Multiple requests over one connection."""
        with IPCClient(ipc_socket_path) as client:
            r1 = client.send({"seq": 1})
            r2 = client.send({"seq": 2})
            r3 = client.send({"seq": 3})
        assert r1["received"]["seq"] == 1
        assert r2["received"]["seq"] == 2
        assert r3["received"]["seq"] == 3

    def test_nested_json_payload(self, ipc_server: subprocess.Popen, ipc_socket_path: str) -> None:
        """Complex nested JSON survives roundtrip."""
        payload = {
            "order": {"symbol": "BTC-USDT", "qty": 1.5},
            "metadata": {"tags": ["a", "b"], "nested": {"deep": True}},
        }
        with IPCClient(ipc_socket_path) as client:
            response = client.send(payload)
        assert response["received"] == payload

    def test_connection_refused_raises(self) -> None:
        """Connecting to non-existent socket raises ConnectionError."""
        client = IPCClient("/tmp/nonexistent-atlas-test.sock")
        with pytest.raises(ConnectionError):
            client.connect()

    def test_send_without_connect_raises(self) -> None:
        """Sending without connecting raises ConnectionError."""
        client = IPCClient("/tmp/fake.sock")
        with pytest.raises(ConnectionError, match="not connected"):
            client.send({"test": True})

    def test_context_manager_closes_on_exception(
        self, ipc_server: subprocess.Popen, ipc_socket_path: str
    ) -> None:
        """Context manager cleans up even if exception occurs."""
        try:
            with IPCClient(ipc_socket_path) as client:
                client.send({"before": "error"})
                raise ValueError("simulated error")
        except ValueError:
            pass
        # Client should be disconnected now
        assert not client.connected

    def test_large_payload(self, ipc_server: subprocess.Popen, ipc_socket_path: str) -> None:
        """Payload near 1MB survives roundtrip."""
        large_data = {"data": "x" * 1_000_000}
        with IPCClient(ipc_socket_path) as client:
            response = client.send(large_data)
        assert len(response["received"]["data"]) == 1_000_000
