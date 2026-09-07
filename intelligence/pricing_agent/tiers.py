# MODULE: atlas-pricing-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# WARNING: No bare except. Deterministic evaluation only.
from __future__ import annotations

import time
import uuid

from .models import AppError, BillingDecision, PricingTier, UsageStats

TIERS: dict[str, PricingTier] = {
    "free": PricingTier(tier="free", max_fps=10, max_bytes_monthly=100 * 1024 * 1024, price_usd=0.0),
    "pro": PricingTier(tier="pro", max_fps=100, max_bytes_monthly=5 * 1024 * 1024 * 1024, price_usd=99.0),
    "enterprise": PricingTier(tier="enterprise", max_fps=-1, max_bytes_monthly=-1, price_usd=999.0),
}


def evaluate_usage(stats: UsageStats, tier_name: str, trace_id: str) -> BillingDecision:
    if tier_name not in TIERS:
        raise AppError("VAL_UNKNOWN_TIER", f"Tier '{tier_name}' not defined", retryable=False)

    tier = TIERS[tier_name]
    max_bytes = tier.max_bytes_monthly
    usage_pct = 0.0
    overage = False

    if max_bytes == -1:
        usage_pct = 0.0
        overage = False
    elif max_bytes == 0:
        raise AppError("VAL_ILLEGAL_TIER_CONFIG", "max_bytes cannot be zero", retryable=False)
    else:
        usage_pct = (stats.bytes_total / max_bytes) * 100.0
        overage = usage_pct > 100.0

    action = "continue"
    if overage:
        action = "suspend" if usage_pct >= 120.0 else "throttle"
    elif usage_pct > 80.0:
        action = "upgrade_prompt"

    return BillingDecision(
        customer_id=stats.customer_id,
        tier=tier_name,
        usage_pct=round(usage_pct, 2),
        overage=overage,
        action=action,
        invoice_usd=tier.price_usd,
        trace_id=trace_id,
        timestamp_ms=int(time.time() * 1000),
    )
