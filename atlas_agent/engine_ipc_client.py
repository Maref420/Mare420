"""IPC Client for Agent ↔ Engine communication over Unix Domain Socket.

GOVERNANCE: Matrix C - Python Agent Layer
CONTRACT: ipc-binary-v1.spec.yaml (length-prefixed frames)
NOTE: Pure transport only. No business logic.

Data Flow:
1. Agent creates IPCClient with socket path
2. connect() opens UDS connection with timeout
3. send(data) serializes dict → JSON → [4B BE len][payload] frame
4. Server processes and responds with same frame format
5. Client deserializes response frame → dict
6. close() or context manager cleans up socket
"""
from __future__ import annotations

import json
import socket
import struct
from typing import Any


class IPCClient:
    """Unix Domain Socket client using length-prefixed binary framing."""

    def __init__(self, path: str = "/tmp/atlas-ipc.sock") -> None:
        self._path: str = path
        self._sock: socket.socket | None = None
        self._timeout: float = 5.0

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> None:
        """Open UDS connection. Raises ConnectionError on failure."""
        if self._sock is not None:
            self.close()
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self._timeout)
            sock.connect(self._path)
            self._sock = sock
        except OSError as e:
            raise ConnectionError(f"failed to connect to {self._path}: {e}") from e

    def send(self, data: dict[str, Any]) -> dict[str, Any]:
        """Send a dict request and receive a dict response.

        Args:
            data: JSON-serializable request payload.

        Returns:
            Parsed JSON response from server.

        Raises:
            ConnectionError: If not connected or socket operation fails.
        """
        if self._sock is None:
            raise ConnectionError("not connected — call connect() first")
        try:
            payload = json.dumps(data).encode("utf-8")
            header = struct.pack(">I", len(payload))
            self._sock.sendall(header + payload)

            # Read response length
            len_buf = self._recv_exact(4)
            resp_len = struct.unpack(">I", len_buf)[0]

            if resp_len == 0 or resp_len > 16_777_216:
                raise ConnectionError(f"invalid response frame length: {resp_len}")

            # Read response payload
            resp_data = self._recv_exact(resp_len)
            result: dict[str, Any] = json.loads(resp_data.decode("utf-8"))
            return result

        except socket.timeout as e:
            self.close()
            raise ConnectionError("socket operation timed out") from e
        except OSError as e:
            self.close()
            raise ConnectionError(f"socket error: {e}") from e
        except (json.JSONDecodeError, struct.error, UnicodeDecodeError) as e:
            self.close()
            raise ConnectionError(f"protocol error: {e}") from e

    def close(self) -> None:
        """Close the socket connection safely."""
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # already closed or not connected
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _recv_exact(self, n: int) -> bytes:
        """Read exactly n bytes from the socket."""
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))  # type: ignore[union-attr]
            if not chunk:
                raise ConnectionError("unexpected EOF while reading from socket")
            buf.extend(chunk)
        return bytes(buf)

    def __enter__(self) -> IPCClient:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.close()
