# MODULE: atlas-customer-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# ADR: docs/decisions/006-governed-memory-system.md
# SECURITY: api_key NEVER logged or returned in full.
# WARNING: No bare except. source_uri mandatory.
from __future__ import annotations

import json
import logging
import signal
import time
from typing import Any

from intelligence.pricing_agent.tiers import TIERS

from .models import (
    AppError,
    CustomerRecord,
    RegistrationRequest,
    RegistrationResponse,
    TierChangeRequest,
    TierChangeResponse,
    mask_api_key,
)
from .store import CustomerStore

logger = logging.getLogger(__name__)


class _StubMemoryStore:
    def append(self, record: dict[str, Any]) -> None:
        logger.info("audit_append", extra={"record": json.dumps(record, default=str)})


class CustomerAgent:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.store_path = config.get("store_path", "./data/customers.json")
        self.store = CustomerStore(path=self.store_path)
        self._memory = _StubMemoryStore()
        self._running = True
        self.agent_id = "customer_agent"
        self._setup_signals()

    def _setup_signals(self) -> None:
        try:
            signal.signal(signal.SIGTERM, self._handle_shutdown)
            signal.signal(signal.SIGINT, self._handle_shutdown)
        except (OSError, ValueError):
            logger.warning("signal_setup_skipped")

    def _handle_shutdown(self, signum: int, frame: Any) -> None:
        logger.info("shutdown_signal", extra={"signum": signum})
        self._running = False

    def register_customer(self, req: RegistrationRequest, trace_id: str) -> RegistrationResponse:
        if req.tier not in TIERS:
            raise AppError("VAL_INVALID_TIER", f"Tier '{req.tier}' not defined", retryable=False)
        if self.store.exists(req.customer_id):
            raise AppError("VAL_DUPLICATE_CUSTOMER", f"Customer '{req.customer_id}' already registered", retryable=False)

        record = CustomerRecord(
            customer_id=req.customer_id,
            api_key=req.api_key,
            tier=req.tier,
            registered_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            status="active",
            source_uri=req.source_uri,
        )
        self.store.add(record)
        self._memory.append({"action": "register", "customer_id": req.customer_id, "trace_id": trace_id})
        masked = mask_api_key(req.api_key)
        logger.info("customer_registered", extra={
            "customer_id": req.customer_id,
            "trace_id": trace_id,
            "masked_key": masked,
        })
        return RegistrationResponse(
            customer_id=req.customer_id,
            status="registered",
            tier=req.tier,
            api_key_prefix=masked,
            message="Customer registered successfully",
        )

    def change_tier(self, customer_id: str, req: TierChangeRequest, trace_id: str) -> TierChangeResponse:
        customer = self.store.get(customer_id)
        if customer is None:
            raise AppError("VAL_CUSTOMER_NOT_FOUND", f"Customer '{customer_id}' not found", retryable=False)
        if req.new_tier not in TIERS:
            raise AppError("VAL_INVALID_TIER", f"Tier '{req.new_tier}' not defined", retryable=False)
        if customer.tier == "enterprise" and req.new_tier != "enterprise":
            raise AppError("BIZ_TIER_DOWNGRADE_BLOCKED", "Enterprise cannot be downgraded", retryable=False)

        old_tier = customer.tier
        self.store.update(customer_id, {"tier": req.new_tier})
        self._memory.append({"action": "tier_change", "customer_id": customer_id, "trace_id": trace_id})

        invoice_usd = TIERS[req.new_tier].price_usd

        logger.info("tier_changed", extra={
            "customer_id": customer_id,
            "old_tier": old_tier,
            "new_tier": req.new_tier,
            "trace_id": trace_id,
        })
        return TierChangeResponse(
            customer_id=customer_id,
            old_tier=old_tier,
            new_tier=req.new_tier,
            action="tier_updated",
            invoice_usd=invoice_usd,
        )

    def suspend_customer(self, customer_id: str, reason: str, trace_id: str) -> None:
        if self.store.get(customer_id) is None:
            raise AppError("VAL_CUSTOMER_NOT_FOUND", f"Customer '{customer_id}' not found", retryable=False)
        self.store.update(customer_id, {"status": "suspended"})
        self._memory.append({"action": "suspend", "customer_id": customer_id, "reason": reason, "trace_id": trace_id})
        logger.info("customer_suspended", extra={"customer_id": customer_id, "trace_id": trace_id})

    def get_customer(self, customer_id: str) -> CustomerRecord | None:
        return self.store.get(customer_id)

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "agent_id": self.agent_id,
            "records_count": len(self.store.list_active()),
            "timestamp_ms": int(time.time() * 1000),
        }
