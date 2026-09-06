#!/usr/bin/env python3
"""Atlas AI Agent HTTP Server.

Governance Reference: CONSTITUTION.md v1.2, MASTER_PROMPT_FULL.md
Module: atlas_agent/http_server.py
Owner: intelligence (Python)
Description: Production-grade HTTP gateway for Agent operations.
             Stdlib-only. No external dependencies.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from atlas_agent.engine_ipc_client import IPCClient
from foundation.metrics.python_metrics import Counter, Gauge, Histogram, MetricsRegistry
from atlas_agent.auth import AuthMiddleware

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error Envelope
# ---------------------------------------------------------------------------

class AppError(Exception):
    """Domain exception with stable error code."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


def create_error_envelope(
    code: str,
    message: str,
    retryable: bool = False,
    trace_id: str = "",
) -> dict[str, Any]:
    return {
        "trace_id": trace_id or str(uuid.uuid4()),
        "service": "agent",
        "code": code,
        "retryable": retryable,
        "http_status": 400 if not retryable else 503,
        "message": message,
        "details": {},
        "cause_chain": [],
        "timestamp_ms": int(time.time() * 1000),
    }


# ---------------------------------------------------------------------------
# Configuration (env-based, typed)
# ---------------------------------------------------------------------------

AGENT_HTTP_PORT: int = int(os.environ.get("AGENT_HTTP_PORT", "8090"))
IPC_SOCKET_PATH: str = os.environ.get("IPC_SOCKET_PATH", "/tmp/atlas-ipc.sock")
ATLAS_MEMORY_DB: str = os.environ.get("ATLAS_MEMORY_DB", "./data/memory.db")
AGENT_REQUEST_TIMEOUT: float = float(os.environ.get("AGENT_REQUEST_TIMEOUT", "5.0"))

# ---------------------------------------------------------------------------
# Global metrics
# ---------------------------------------------------------------------------

_metrics_registry = MetricsRegistry()
_requests_total = Counter("agent_http_requests_total", "Total HTTP requests")
_request_duration = Histogram("agent_http_request_duration_seconds", "Request duration")
_active_connections = Gauge("agent_http_active_connections", "Active connections")
_metrics_registry.register(_requests_total)
_metrics_registry.register(_request_duration)
_metrics_registry.register(_active_connections)

_shutdown_event = threading.Event()
_auth_middleware = AuthMiddleware()


# ---------------------------------------------------------------------------
# Request Handler
# ---------------------------------------------------------------------------

class AgentHTTPRequestHandler(BaseHTTPRequestHandler):
    """Handles all Agent HTTP endpoints."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # Suppress default stderr; we use structured logging

    def _get_trace_id(self) -> str:
        return self.headers.get("X-Trace-Id") or str(uuid.uuid4())

    def _send_json(self, status: int, body: Any, trace_id: str) -> None:
        payload = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Trace-Id", trace_id)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, status: int, text: str, trace_id: str) -> None:
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("X-Trace-Id", trace_id)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    # -- routing --------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        self._route("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._route("POST")

    def _route(self, method: str) -> None:
        start = time.monotonic()
        trace_id = self._get_trace_id()
        path = self.path.split("?")[0]
        _active_connections.inc()
        status_code = 500

        # Auth check
        req_headers = {k: v for k, v in self.headers.items()}
        allowed, auth_err = _auth_middleware.check(req_headers, path, trace_id)
        if not allowed and auth_err is not None:
            self._send_json(auth_err["http_status"], auth_err, trace_id)
            status_code = auth_err["http_status"]
            return

        try:
            if method == "GET" and path == "/health/live":
                self._send_json(200, {"status": "alive"}, trace_id)
                status_code = 200
            elif method == "GET" and path == "/health/ready":
                status_code = self._handle_ready(trace_id)
            elif method == "GET" and path == "/metrics":
                self._send_text(200, _metrics_registry.export_prometheus(), trace_id)
                status_code = 200
            elif method == "POST" and path == "/assess":
                status_code = self._handle_assess(trace_id)
            else:
                err = create_error_envelope("VAL_INVALID_PATH", "Not found", trace_id=trace_id)
                self._send_json(404, err, trace_id)
                status_code = 404
        except Exception as exc:
            logger.error("unhandled_error", extra={"trace_id": trace_id, "error": str(exc)})
            err = create_error_envelope("INT_INVARIANT_BROKEN", "Internal error", trace_id=trace_id)
            self._send_json(500, err, trace_id)
            status_code = 500
        finally:
            _active_connections.dec()
            duration = time.monotonic() - start
            _request_duration.observe(duration)
            _requests_total.increment()
            logger.info(
                "request_complete",
                extra={
                    "method": method,
                    "path": path,
                    "status": status_code,
                    "duration_ms": round(duration * 1000, 2),
                    "trace_id": trace_id,
                },
            )

    # -- endpoints ------------------------------------------------------

    def _handle_ready(self, trace_id: str) -> int:
        ipc_ok = os.path.exists(IPC_SOCKET_PATH)
        db_ok = os.path.isdir(os.path.dirname(ATLAS_MEMORY_DB)) or os.path.isfile(ATLAS_MEMORY_DB)
        if ipc_ok and db_ok:
            self._send_json(200, {"status": "ready"}, trace_id)
            return 200
        details: dict[str, bool] = {"ipc_socket": ipc_ok, "memory_db": db_ok}
        err = create_error_envelope(
            "DEP_NOT_READY",
            "Dependencies not ready",
            retryable=True,
            trace_id=trace_id,
        )
        err["details"] = details
        self._send_json(503, err, trace_id)
        return 503

    def _handle_assess(self, trace_id: str) -> int:
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            payload = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            err = create_error_envelope("VAL_INVALID_INPUT", "Invalid JSON", trace_id=trace_id)
            self._send_json(400, err, trace_id)
            return 400

        if not isinstance(payload, dict):
            err = create_error_envelope("VAL_INVALID_INPUT", "Payload must be object", trace_id=trace_id)
            self._send_json(400, err, trace_id)
            return 400

        if "order" not in payload:
            err = create_error_envelope("VAL_MISSING_ORDER", "Missing field: order", trace_id=trace_id)
            self._send_json(400, err, trace_id)
            return 400

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                with IPCClient(IPC_SOCKET_PATH) as ipc:
                    response = ipc.send(payload)
                self._send_json(200, response, trace_id)
                return 200
            except AppError as exc:
                if exc.retryable and attempt < max_attempts - 1:
                    time.sleep(min(1.0, 0.1 * (2 ** attempt)))
                    continue
                err = create_error_envelope(exc.code, exc.message, retryable=exc.retryable, trace_id=trace_id)
                self._send_json(502, err, trace_id)
                return 502
            except TimeoutError:
                err = create_error_envelope("NET_UPSTREAM_TIMEOUT", "IPC timeout", retryable=True, trace_id=trace_id)
                self._send_json(504, err, trace_id)
                return 504
            except Exception:
                if attempt < max_attempts - 1:
                    time.sleep(min(1.0, 0.1 * (2 ** attempt)))
                    continue
                err = create_error_envelope("NET_COMMUNICATION", "IPC failure", retryable=True, trace_id=trace_id)
                self._send_json(502, err, trace_id)
                return 502
        return 502  # unreachable but satisfies type checker


# ---------------------------------------------------------------------------
# Server + Lifecycle
# ---------------------------------------------------------------------------

class AgentHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _graceful_shutdown(signum: int, _frame: Any) -> None:
    logger.info("shutdown_signal", extra={"signal": signum})
    _shutdown_event.set()


def main() -> None:
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)

    server = AgentHTTPServer(("0.0.0.0", AGENT_HTTP_PORT), AgentHTTPRequestHandler)
    logger.info(
        "server_starting",
        extra={"port": AGENT_HTTP_PORT, "ipc": IPC_SOCKET_PATH, "db": ATLAS_MEMORY_DB},
    )

    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    try:
        while not _shutdown_event.is_set():
            _shutdown_event.wait(timeout=0.5)
    finally:
        logger.info("server_shutting_down")
        server.shutdown()
        worker.join(timeout=3)
        logger.info("server_stopped")


if __name__ == "__main__":
    main()
