# MODULE: atlas-pricing-agent
# TEST TYPE: Unit tests
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from intelligence.pricing_agent.agent import PricingAgent
from intelligence.pricing_agent.models import AppError, BillingDecision, CustomerRecord, UsageStats
from intelligence.pricing_agent.tiers import evaluate_usage


@pytest.fixture
def usage_50mb() -> UsageStats:
    return UsageStats(customer_id="c1", frames_total=500, bytes_total=50 * 1024 * 1024, dropped_frames=0, last_frame_at="2025-01-01T00:00:00Z")


@pytest.fixture
def agent() -> PricingAgent:
    return PricingAgent({"gateway_url": "http://mock:8443", "api_key": "k", "customer_store_path": "/nonexistent"})


def test_free_within_limits(usage_50mb: UsageStats) -> None:
    d = evaluate_usage(usage_50mb, "free", "t1")
    assert d.action == "continue"
    assert d.overage is False


def test_free_overage_throttle() -> None:
    s = UsageStats(customer_id="t", frames_total=1, bytes_total=110 * 1024 * 1024, dropped_frames=0, last_frame_at="2025-01-01T00:00:00Z")
    d = evaluate_usage(s, "free", "t2")
    assert d.action == "throttle"
    assert d.overage is True


def test_free_overage_suspend() -> None:
    s = UsageStats(customer_id="t", frames_total=1, bytes_total=125 * 1024 * 1024, dropped_frames=0, last_frame_at="2025-01-01T00:00:00Z")
    d = evaluate_usage(s, "free", "t3")
    assert d.action == "suspend"


def test_pro_normal() -> None:
    s = UsageStats(customer_id="t", frames_total=1, bytes_total=100 * 1024 * 1024, dropped_frames=0, last_frame_at="2025-01-01T00:00:00Z")
    d = evaluate_usage(s, "pro", "t4")
    assert d.action == "continue"


def test_pro_upgrade_prompt() -> None:
    s = UsageStats(customer_id="t", frames_total=1, bytes_total=4200 * 1024 * 1024, dropped_frames=0, last_frame_at="2025-01-01T00:00:00Z")
    d = evaluate_usage(s, "pro", "t5")
    assert d.action == "upgrade_prompt"
    assert d.overage is False


def test_enterprise_unlimited() -> None:
    s = UsageStats(customer_id="t", frames_total=1, bytes_total=999 * 1024 * 1024 * 1024, dropped_frames=0, last_frame_at="2025-01-01T00:00:00Z")
    d = evaluate_usage(s, "enterprise", "t6")
    assert d.action == "continue"
    assert d.usage_pct == 0.0


def test_unknown_tier_raises() -> None:
    s = UsageStats(customer_id="t", frames_total=1, bytes_total=1, dropped_frames=0, last_frame_at="2025-01-01T00:00:00Z")
    with pytest.raises(AppError) as exc:
        evaluate_usage(s, "invalid", "t7")
    assert exc.value.code == "VAL_UNKNOWN_TIER"


def test_models_frozen() -> None:
    s = UsageStats(customer_id="t", frames_total=1, bytes_total=1, dropped_frames=0, last_frame_at="2025-01-01T00:00:00Z")
    with pytest.raises(Exception):
        s.bytes_total = 999  # type: ignore[misc]


def test_health_check(agent: PricingAgent) -> None:
    h = agent.health_check()
    assert h["status"] == "healthy"


def test_fetch_usage_connection_error(agent: PricingAgent) -> None:
    with patch("httpx.Client") as mock_cls:
        mc = MagicMock()
        mc.__enter__ = MagicMock(return_value=mc)
        mc.__exit__ = MagicMock(return_value=False)
        mc.get.side_effect = httpx.ConnectError("refused")
        mock_cls.return_value = mc
        with pytest.raises(AppError) as exc:
            agent.fetch_usage("c1", "t8")
        assert exc.value.code == "DEP_CONNECTION_FAILED"
        assert exc.value.retryable is True


def test_process_all_empty(agent: PricingAgent) -> None:
    decisions = agent.process_all_customers("t9")
    assert decisions == []
