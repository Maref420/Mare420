# MODULE: atlas-customer-agent
# TEST TYPE: Unit tests
from __future__ import annotations

import json
import os

import pytest

from intelligence.customer_agent.agent import CustomerAgent
from intelligence.customer_agent.models import (
    AppError,
    CustomerRecord,
    RegistrationRequest,
    TierChangeRequest,
    mask_api_key,
)
from intelligence.customer_agent.store import CustomerStore


@pytest.fixture
def tmp_store(tmp_path) -> str:
    return str(tmp_path / "customers.json")


@pytest.fixture
def agent(tmp_store) -> CustomerAgent:
    return CustomerAgent({"store_path": tmp_store})


SAMPLE_KEY = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"


def test_register_success(agent, tmp_store) -> None:
    req = RegistrationRequest(customer_id="c1", api_key=SAMPLE_KEY, tier="pro", source_uri="test://src")
    resp = agent.register_customer(req, "t1")
    assert resp.status == "registered"
    assert resp.api_key_prefix == mask_api_key(SAMPLE_KEY)
    assert os.path.exists(tmp_store)


def test_register_duplicate(agent) -> None:
    req = RegistrationRequest(customer_id="c1", api_key=SAMPLE_KEY, tier="free", source_uri="test://src")
    agent.register_customer(req, "t1")
    with pytest.raises(AppError) as exc:
        agent.register_customer(req, "t2")
    assert exc.value.code == "VAL_DUPLICATE_CUSTOMER"


def test_register_invalid_tier(agent) -> None:
    req = RegistrationRequest(customer_id="c1", api_key=SAMPLE_KEY, tier="invalid", source_uri="test://src")
    with pytest.raises(AppError) as exc:
        agent.register_customer(req, "t1")
    assert exc.value.code == "VAL_INVALID_TIER"


def test_change_tier_upgrade(agent) -> None:
    req = RegistrationRequest(customer_id="c1", api_key=SAMPLE_KEY, tier="free", source_uri="test://src")
    agent.register_customer(req, "t1")
    tier_req = TierChangeRequest(new_tier="pro", reason="upgrade", source_uri="test://src")
    resp = agent.change_tier("c1", tier_req, "t2")
    assert resp.old_tier == "free"
    assert resp.new_tier == "pro"


def test_change_tier_downgrade_enterprise_blocked(agent) -> None:
    req = RegistrationRequest(customer_id="c1", api_key=SAMPLE_KEY, tier="enterprise", source_uri="test://src")
    agent.register_customer(req, "t1")
    tier_req = TierChangeRequest(new_tier="pro", reason="down", source_uri="test://src")
    with pytest.raises(AppError) as exc:
        agent.change_tier("c1", tier_req, "t2")
    assert exc.value.code == "BIZ_TIER_DOWNGRADE_BLOCKED"


def test_suspend_customer(agent) -> None:
    req = RegistrationRequest(customer_id="c1", api_key=SAMPLE_KEY, tier="pro", source_uri="test://src")
    agent.register_customer(req, "t1")
    agent.suspend_customer("c1", "violation", "t2")
    c = agent.get_customer("c1")
    assert c is not None
    assert c.status == "suspended"


def test_store_atomic_write(tmp_store) -> None:
    store = CustomerStore(path=tmp_store)
    rec = CustomerRecord(customer_id="a1", api_key=SAMPLE_KEY, tier="free", registered_at="2025-01-01T00:00:00Z", status="active", source_uri="test://src")
    store.add(rec)
    tmp_files = [f for f in os.listdir(os.path.dirname(tmp_store)) if f.endswith(".tmp")]
    assert len(tmp_files) == 0
    assert os.path.exists(tmp_store)


def test_api_key_masked_in_response(agent) -> None:
    req = RegistrationRequest(customer_id="c1", api_key=SAMPLE_KEY, tier="pro", source_uri="test://src")
    resp = agent.register_customer(req, "t1")
    assert SAMPLE_KEY not in json.dumps(resp.model_dump())


def test_health_check(agent) -> None:
    h = agent.health_check()
    assert h["status"] == "healthy"
    assert h["agent_id"] == "customer_agent"


def test_models_frozen() -> None:
    req = RegistrationRequest(customer_id="c1", api_key=SAMPLE_KEY, tier="pro", source_uri="test://src")
    with pytest.raises(Exception):
        req.customer_id = "changed"  # type: ignore[misc]
