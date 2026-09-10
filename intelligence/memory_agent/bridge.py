# MODULE: atlas-memory-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: Subprocess IPC bridge to Rust memory_store binary.
# WARNING: No bare except. All errors mapped to MemoryStoreError.
from __future__ import annotations

import contextlib
import json
import select
import subprocess
import threading
from pathlib import Path
from typing import Any

from .store import MemoryStoreError


def _find_ipc_binary() -> str:
    candidates = [
        Path("core_engine/memory_store/target/release/ipc_server"),
        Path("core_engine/memory_store/target/debug/ipc_server"),
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    raise MemoryStoreError(
        "DEP_STORE_UNAVAILABLE",
        "Rust IPC binary not found. Run: cargo build --bin ipc_server",
        True,
    )


class RustIpcBridge:
    """Single shared subprocess IPC bridge.

    Per OG architecture decision: one shared Rust subprocess should be passed
    to agents instead of one subprocess per agent. This bridge serializes IPC
    requests with a lock and enforces response timeouts.
    """

    def __init__(
        self,
        binary_path: str | None = None,
        response_timeout_secs: float = 5.0,
    ) -> None:
        self._binary = binary_path or _find_ipc_binary()
        self._response_timeout_secs = response_timeout_secs
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._started = False

    def _start_locked(self) -> None:
        """Start process. Caller must hold self._lock."""
        if self._started and self._proc is not None and self._proc.poll() is None:
            return
        try:
            self._proc = subprocess.Popen(
                [self._binary],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            self._started = True
        except OSError as e:
            raise MemoryStoreError(
                "DEP_STORE_UNAVAILABLE",
                f"failed to start IPC: {e}",
                True,
            ) from e

    def start(self) -> None:
        with self._lock:
            self._start_locked()

    def _stop_locked(self) -> None:
        """Stop process. Caller must hold self._lock."""
        if self._proc is None:
            self._started = False
            return

        if self._proc.stdin is not None:
            with contextlib.suppress(OSError):
                self._proc.stdin.close()

        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=2)

        self._proc = None
        self._started = False

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def send_command(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if not self._started or self._proc is None or self._proc.poll() is not None:
                self._start_locked()

            if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
                raise MemoryStoreError(
                    "DEP_STORE_UNAVAILABLE",
                    "IPC process not available",
                    True,
                )

            request = json.dumps({"cmd": cmd, "payload": payload}) + "\n"

            try:
                self._proc.stdin.write(request.encode("utf-8"))
                self._proc.stdin.flush()
            except BrokenPipeError as e:
                self._started = False
                raise MemoryStoreError(
                    "DEP_STORE_UNAVAILABLE",
                    "IPC pipe broken",
                    True,
                ) from e
            except OSError as e:
                self._started = False
                raise MemoryStoreError(
                    "DEP_STORE_UNAVAILABLE",
                    f"IPC write error: {e}",
                    True,
                ) from e

            try:
                fd = self._proc.stdout.fileno()
                ready, _, _ = select.select([fd], [], [], self._response_timeout_secs)
                if not ready:
                    self._stop_locked()
                    raise MemoryStoreError(
                        "DEP_STORE_TIMEOUT",
                        f"IPC response timeout after {self._response_timeout_secs}s",
                        True,
                    )

                line = self._proc.stdout.readline()
                if not line:
                    self._started = False
                    raise MemoryStoreError(
                        "DEP_STORE_UNAVAILABLE",
                        "IPC closed stdout",
                        True,
                    )

                response = json.loads(line.decode("utf-8"))
                if not isinstance(response, dict):
                    raise MemoryStoreError(
                        "INT_INVARIANT_BROKEN",
                        "IPC response is not an object",
                        False,
                    )
                return response

            except json.JSONDecodeError as e:
                raise MemoryStoreError(
                    "INT_INVARIANT_BROKEN",
                    f"invalid JSON: {e}",
                    False,
                ) from e
            except OSError as e:
                self._started = False
                raise MemoryStoreError(
                    "DEP_STORE_UNAVAILABLE",
                    f"IPC read error: {e}",
                    True,
                ) from e

    def write_node(self, node_data: dict[str, Any]) -> None:
        resp = self.send_command("write", node_data)
        if not resp.get("ok"):
            err = resp.get("error", {})
            raise MemoryStoreError(
                err.get("code", "INT_INVARIANT_BROKEN"),
                err.get("message", "unknown"),
                err.get("retryable", False),
            )

    def read_node(self, node_id: str) -> dict[str, Any] | None:
        resp = self.send_command("read", {"node_id": node_id})
        if not resp.get("ok"):
            err = resp.get("error", {})
            if err.get("code") == "VAL_TTL_EXPIRED":
                return None
            raise MemoryStoreError(
                err.get("code", "INT_INVARIANT_BROKEN"),
                err.get("message", "unknown"),
                err.get("retryable", False),
            )

        data = resp.get("data")
        if isinstance(data, dict):
            return data
        return None

    def search(self, keyword: str) -> list[dict[str, Any]]:
        resp = self.send_command("search", {"keyword": keyword})
        if not resp.get("ok"):
            err = resp.get("error", {})
            raise MemoryStoreError(
                err.get("code", "INT_INVARIANT_BROKEN"),
                err.get("message", "unknown"),
                err.get("retryable", False),
            )

        data = resp.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def stats(self) -> dict[str, Any]:
        resp = self.send_command("stats", {})
        if not resp.get("ok"):
            err = resp.get("error", {})
            raise MemoryStoreError(
                err.get("code", "INT_INVARIANT_BROKEN"),
                err.get("message", "unknown"),
                err.get("retryable", False),
            )

        data = resp.get("data")
        if isinstance(data, dict):
            return data
        return {}

    def evict(self) -> int:
        resp = self.send_command("evict", {})
        if not resp.get("ok"):
            return 0

        data = resp.get("data")
        if isinstance(data, dict):
            evicted = data.get("evicted", 0)
            if isinstance(evicted, int):
                return evicted
        return 0

    def __del__(self) -> None:
        self.stop()
