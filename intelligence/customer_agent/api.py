# MODULE: atlas-customer-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# WARNING: No stack traces in responses. No bare except.
from __future__ import annotations

import json
import logging
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

from .agent import CustomerAgent
from .models import (
    AppError,
    RegistrationRequest,
    TierChangeRequest,
    mask_api_key,
)

logger = logging.getLogger(__name__)


class LandingHandler(BaseHTTPRequestHandler):
    agent: CustomerAgent

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress default logging; use structured logging

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body, default=str).encode("utf-8"))

    def _send_error_envelope(self, status: int, code: str, message: str, retryable: bool, trace_id: str) -> None:
        self._send_json(status, {
            "service": "customer_agent",
            "code": code,
            "retryable": retryable,
            "http_status": status,
            "message": message,
            "trace_id": trace_id,
        })

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _get_trace_id(self) -> str:
        return self.headers.get("X-Trace-ID", str(uuid.uuid4()))

    def do_POST(self) -> None:
        trace_id = self._get_trace_id()
        path = urlparse(self.path).path
        try:
            body = self._read_body()
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_error_envelope(400, "VAL_INVALID_JSON", "Invalid request body", False, trace_id)
            return

        try:
            if path == "/v1/customers/register":
                req = RegistrationRequest.model_validate(body)
                resp = self.agent.register_customer(req, trace_id)
                self._send_json(201, resp.model_dump())
            elif path.startswith("/v1/customers/") and path.endswith("/tier"):
                parts = path.strip("/").split("/")
                if len(parts) != 4:
                    self._send_error_envelope(404, "VAL_NOT_FOUND", "Not found", False, trace_id)
                    return
                customer_id = parts[2]
                req = TierChangeRequest.model_validate(body)
                resp = self.agent.change_tier(customer_id, req, trace_id)
                self._send_json(200, resp.model_dump())
            else:
                self._send_error_envelope(404, "VAL_NOT_FOUND", "Not found", False, trace_id)
        except AppError as e:
            status = 400 if e.code.startswith(("VAL_", "BIZ_")) else 503
            self._send_error_envelope(status, e.code, str(e), e.retryable, trace_id)
        except ValueError as e:
            self._send_error_envelope(400, "VAL_SCHEMA_ERROR", str(e), False, trace_id)
        except OSError:
            self._send_error_envelope(503, "INT_IO_ERROR", "Internal error", False, trace_id)

    def do_GET(self) -> None:
        trace_id = self._get_trace_id()
        path = urlparse(self.path).path
        try:
            if path == "/health/live":
                self._send_json(200, {"status": "alive"})
            elif path == "/health/ready":
                self._send_json(200, {"status": "ready"})
            elif path.startswith("/v1/customers/"):
                parts = path.strip("/").split("/")
                if len(parts) != 3:
                    self._send_error_envelope(404, "VAL_NOT_FOUND", "Not found", False, trace_id)
                    return
                customer_id = parts[2]
                customer = self.agent.get_customer(customer_id)
                if customer is None:
                    self._send_error_envelope(404, "VAL_CUSTOMER_NOT_FOUND", "Not found", False, trace_id)
                    return
                data = customer.model_dump()
                data["api_key"] = mask_api_key(data["api_key"])
                self._send_json(200, data)
            else:
                self._send_error_envelope(404, "VAL_NOT_FOUND", "Not found", False, trace_id)
        except AppError as e:
            self._send_error_envelope(500, e.code, str(e), e.retryable, trace_id)
        except OSError:
            self._send_error_envelope(503, "INT_IO_ERROR", "Internal error", False, trace_id)


class LandingServer:
    def __init__(self, agent: CustomerAgent, port: int = 8095) -> None:
        self.agent = agent
        self.port = port
        self._server: HTTPServer | None = None

    def start(self) -> None:
        handler = type("H", (LandingHandler,), {"agent": self.agent})
        self._server = HTTPServer(("0.0.0.0", self.port), handler)
        logger.info("landing_server_started", extra={"port": self.port})
        self._server.serve_forever()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            logger.info("landing_server_stopped")
