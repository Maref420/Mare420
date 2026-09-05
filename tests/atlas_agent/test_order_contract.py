"""Schema parity tests for Order v1.0 and EngineMessage envelope.
Source: contracts/schemas/execution/order-v1.json
        governance/schemas/engine-contract-v1.json
"""
import json
import pytest
from uuid import uuid4
from datetime import datetime, timezone
from atlas_agent.models import (
    Order, OrderSide, OrderType, TimeInForce,
    EngineMessage, MessageMetadata,
)

def make_valid_order() -> Order:
    return Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=1.5,
        order_type=OrderType.MARKET,
        agent_id="test-agent",
    )

def test_order_json_roundtrip():
    order = make_valid_order()
    data = order.model_dump_json()
    restored = Order.model_validate_json(data)
    assert order == restored

def test_order_rejects_unknown_fields():
    with pytest.raises(Exception):
        Order(
            symbol="BTCUSDT", side=OrderSide.BUY, quantity=1.0,
            order_type=OrderType.MARKET, agent_id="a",
            bad_field=True,
        )

def test_order_rejects_zero_quantity():
    with pytest.raises(Exception):
        Order(symbol="BTC", side=OrderSide.BUY, quantity=0.0,
             order_type=OrderType.MARKET, agent_id="a")

def test_order_rejects_empty_symbol():
    with pytest.raises(Exception):
        Order(symbol="", side=OrderSide.BUY, quantity=1.0,
             order_type=OrderType.MARKET, agent_id="a")

def test_envelope_wraps_order():
    order = make_valid_order()
    msg = EngineMessage.wrap_order(order, "test-agent")
    assert msg.contract_version == "1.0"
    assert msg.source_engine == "python_engine"
    assert msg.message_type == "exec.order.v1"
    assert msg.metadata.owner == "Python AI Agent"
    assert "symbol" in msg.payload

def test_envelope_json_serializable():
    order = make_valid_order()
    msg = EngineMessage.wrap_order(order, "test-agent")
    data = msg.model_dump_json()
    parsed = json.loads(data)
    assert parsed["contract_version"] == "1.0"
    assert "payload" in parsed

def test_envelope_rejects_unknown_fields():
    with pytest.raises(Exception):
        EngineMessage(
            contract_version="1.0", message_type="x",
            source_engine="python_engine", payload={},
            metadata=MessageMetadata(
                specification_id="s", policy_version="1.0",
                owner="o", validation_status="v",
            ),
            bad_field=True,
        )
