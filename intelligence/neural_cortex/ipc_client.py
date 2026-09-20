"""
UDS IPC Client for communicating with Rust IPC Server.
Implements exact binary protocol: 4-byte BE u32 length prefix + JSON payload.

Governed by:
- ipc-binary-v1.spec.yaml contract
- ATLAS Protocol Rule 12 (Minimal Blast Radius)
- Cross-language contract purity
"""
from __future__ import annotations

import contextlib
import json
import logging
import socket
import struct
from typing import Any, cast

logger = logging.getLogger(__name__)

MAX_FRAME_SIZE = 16_777_216  # 16MB, matches Rust IPC server limit


class IpcClient:
    """
    Unix Domain Socket client implementing Atlas IPC binary protocol.
    Thread-safe for single-connection usage.
    """

    def __init__(self, socket_path: str = "/app/uds/atlas-ipc.sock") -> None:
        self._socket_path = socket_path
        self._sock: socket.socket | None = None

    def connect(self) -> bool:
        """Establish UDS connection to IPC server."""
        try:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.connect(self._socket_path)
            logger.info("IPC_CLIENT_CONNECTED", extra={"path": self._socket_path})
            return True
        except (OSError, ConnectionRefusedError) as e:
            logger.error("IPC_CLIENT_CONNECT_FAILED", extra={"error": str(e)})
            self._sock = None
            return False

    def disconnect(self) -> None:
        """Close UDS connection gracefully."""
        if self._sock is not None:
            with contextlib.suppress(OSError):
                self._sock.close()
            self._sock = None
            logger.info("IPC_CLIENT_DISCONNECTED")

    def send_request(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """
        Send a request using binary length-prefixed frame protocol.

        Wire format:
            [4 bytes: u32 big-endian length] [N bytes: JSON payload]

        Args:
            payload: Dictionary to serialize as JSON and send.

        Returns:
            Parsed JSON response dictionary, or None on failure.
        """
        if self._sock is None:
            logger.warning("IPC_SEND_SKIPPED: not connected")
            return None

        try:
            json_bytes = json.dumps(payload).encode("utf-8")
            frame_length = len(json_bytes)

            if frame_length == 0 or frame_length > MAX_FRAME_SIZE:
                logger.error(
                    "IPC_INVALID_FRAME_SIZE",
                    extra={"size": frame_length},
                )
                return None

            # Write 4-byte big-endian length prefix
            length_prefix = struct.pack(">I", frame_length)
            self._sock.sendall(length_prefix + json_bytes)

            # Read 4-byte response length prefix
            resp_len_bytes = self._recv_exact(4)
            if resp_len_bytes is None:
                return None

            resp_length = struct.unpack(">I", resp_len_bytes)[0]

            if resp_length == 0 or resp_length > MAX_FRAME_SIZE:
                logger.error(
                    "IPC_INVALID_RESPONSE_SIZE",
                    extra={"size": resp_length},
                )
                return None

            # Read response payload
            resp_bytes = self._recv_exact(resp_length)
            if resp_bytes is None:
                return None

            raw_response = json.loads(resp_bytes.decode("utf-8"))
            response: dict[str, Any] = cast(dict[str, Any], raw_response)
            return response

        except (OSError, json.JSONDecodeError, struct.error) as e:
            logger.error("IPC_REQUEST_FAILED", extra={"error": str(e)})
            return None

    def _recv_exact(self, num_bytes: int) -> bytes | None:
        """
        Read exactly num_bytes from socket.
        Handles partial reads and interrupted syscalls.
        """
        if self._sock is None:
            return None

        buffer = bytearray()
        while len(buffer) < num_bytes:
            try:
                chunk = self._sock.recv(num_bytes - len(buffer))
                if not chunk:
                    logger.error("IPC_CONNECTION_CLOSED_UNEXPECTEDLY")
                    return None
                buffer.extend(chunk)
            except OSError as e:
                logger.error("IPC_RECV_ERROR", extra={"error": str(e)})
                return None

        return bytes(buffer)
