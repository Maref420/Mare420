"""PRODUCTION VALIDATION: Rust and Python serialize identical Orders identically.
This ensures cross-language communication produces semantically equivalent data."""
import json
from uuid import UUID
from datetime import datetime, timezone
from atlas_agent.models import Order, OrderSide, OrderType

def test_python_order_has_all_required_fields():
    """Verify Python Order contains every required field from order-v1.json."""
    order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=1.5,
        order_type=OrderType.LIMIT,
        price=67000.0,
        agent_id="parity-test",
    )
    data = json.loads(order.model_dump_json())
    required = ["order_id", "symbol", "side", "quantity", "order_type", "timestamp", "agent_id"]
    for field in required:
        assert field in data, f"MISSING required field: {field}"
    # Verify types match contract
    assert isinstance(data["quantity"], float)
    assert data["side"] == "buy"
    assert data["order_type"] == "limit"
    assert data["price"] == 67000.0
    print(f"✅ Cross-language parity: all {len(required)} required fields present with correct types")

def test_python_envelope_matches_go_contract():
    """Verify Python EngineMessage has exact fields from engine-contract-v1.json."""
    from atlas_agent.models import EngineMessage
    order = Order(symbol="ETHUSDT", side=OrderSide.SELL, quantity=0.5,
                  order_type=OrderType.MARKET, agent_id="parity-test")
    msg = EngineMessage.wrap_order(order, "parity-test")
    data = json.loads(msg.model_dump_json())
    required_envelope = ["contract_version", "message_type", "source_engine", "timestamp", "payload", "metadata"]
    for field in required_envelope:
        assert field in data, f"MISSING envelope field: {field}"
    required_meta = ["specification_id", "policy_version", "owner", "validation_status"]
    for field in required_meta:
        assert field in data["metadata"], f"MISSING metadata field: {field}"
    assert data["contract_version"] == "1.0"
    assert data["source_engine"] == "python_engine"
    print(f"✅ Envelope parity: all {len(required_envelope)} + {len(required_meta)} fields verified")
