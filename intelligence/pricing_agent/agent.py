# MODULE: atlas-pricing-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# ADR: docs/decisions/006-governed-memory-system.md
# WARNING: No bare except. httpx timeout mandatory. source_uri mandatory.
from __future__ import annotations

import json
import logging
import signal
import time
from pathlib import Path
from typing import Any

import httpx

from .models import AppError, BillingDecision, CustomerRecord, UsageStats
from .tiers import evaluate_usage

logger = logging.getLogger(__name__)


class _StubMemoryStore:
    def append(self, record: dict[str, Any]) -> None:
        logger.info("audit_append", extra={"record": json.dumps(record, default=str)})


class PricingAgent:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.gateway_url = config.get("gateway_url", "http://localhost:8443").rstrip("/")
        self.api_key = config.get("api_key", "")
        self.store_path = config.get("customer_store_path", "./data/customers.json")
        self._memory = _StubMemoryStore()
        self._customers: list[CustomerRecord] = []
        self._running = True
        self._load_customers()
        self._setup_signals()

    def _load_customers(self) -> None:
        path = Path(self.store_path)
        if not path.exists():
            logger.warning("customer_store_missing", extra={"path": str(path)})
            return
        try:
            raw = path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            self._customers = [CustomerRecord.model_validate(c) for c in parsed]
            logger.info("customers_loaded", extra={"count": len(self._customers)})
        except json.JSONDecodeError as e:
            raise AppError("INT_INVALID_STORE", "Invalid JSON in customer store", retryable=False) from e
        except OSError as e:
            raise AppError("INT_STORE_IO", "Cannot read customer store", retryable=False) from e
        except ValueError as e:
            raise AppError("VAL_STORE_SCHEMA", "Schema validation failed", retryable=False) from e

    def fetch_usage(self, customer_id: str, trace_id: str) -> UsageStats:
        if not customer_id:
            raise AppError("VAL_EMPTY_CUSTOMER_ID", "customer_id required", retryable=False)
        url = f"{self.gateway_url}/v1/usage"
        headers = {"X-API-Key": self.api_key, "X-Trace-ID": trace_id}
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                return UsageStats.model_validate(resp.json())
        except httpx.HTTPStatusError as e:
            raise AppError(f"DEP_HTTP_{e.response.status_code}", "Gateway error", retryable=True) from e
        except httpx.ConnectError as e:
            raise AppError("DEP_CONNECTION_FAILED", "Gateway unreachable", retryable=True) from e
        except httpx.TimeoutException as e:
            raise AppError("DEP_TIMEOUT", "Gateway timeout", retryable=True) from e
        except ValueError as e:
            raise AppError("VAL_USAGE_SCHEMA", "Invalid usage response", retryable=False) from e

    def evaluate_customer(self, customer_id: str, trace_id: str) -> BillingDecision:
        stats = self.fetch_usage(customer_id, trace_id)
        customer = next((c for c in self._customers if c.customer_id == customer_id), None)
        if customer is None:
            raise AppError("VAL_CUSTOMER_NOT_FOUND", f"Customer {customer_id} not found", retryable=False)
        decision = evaluate_usage(stats, customer.tier, trace_id)
        self._memory.append({"customer_id": customer_id, "trace_id": trace_id, "decision": decision.model_dump()})
        logger.info("customer_evaluated", extra={"customer_id": customer_id, "action": decision.action})
        return decision

    def process_all_customers(self, trace_id: str) -> list[BillingDecision]:
        decisions: list[BillingDecision] = []
        for cust in self._customers:
            try:
                decisions.append(self.evaluate_customer(cust.customer_id, trace_id))
            except AppError as e:
                logger.error("process_failed", extra={"customer_id": cust.customer_id, "code": e.code})
                decisions.append(BillingDecision(
                    customer_id=cust.customer_id, tier=cust.tier, usage_pct=0.0,
                    overage=False, action="suspend", invoice_usd=0.0,
                    trace_id=trace_id, timestamp_ms=int(time.time() * 1000),
                ))
        return decisions

    def health_check(self) -> dict[str, Any]:
        return {"status": "healthy", "service": "pricing_agent", "customers": len(self._customers), "timestamp_ms": int(time.time() * 1000)}

    def _setup_signals(self) -> None:
        try:
            signal.signal(signal.SIGTERM, lambda *_: setattr(self, '_running', False))
            signal.signal(signal.SIGINT, lambda *_: setattr(self, '_running', False))
        except (ValueError, OSError):
            logger.warning("signal_setup_skipped")
