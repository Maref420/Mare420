"""End-to-End Integration Test: Python → Go Broker.
Verifies that Python can create an Order, wrap it in an EngineMessage,
and successfully publish to the Go Message Broker /publish endpoint.

Prerequisites: Go Broker must be running on localhost:8090
"""
import json
import urllib.request
import urllib.error
import sys
from atlas_agent.models import Order, OrderSide, OrderType, EngineMessage

BROKER_URL = "http://localhost:8090/publish"

def test_e2e_publish_order():
    order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.5,
        order_type=OrderType.MARKET,
        agent_id="e2e-test-agent",
    )
    msg = EngineMessage.wrap_order(order, "e2e-test-agent")
    payload = msg.model_dump_json().encode("utf-8")
    req = urllib.request.Request(
        BROKER_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            body = json.loads(resp.read().decode("utf-8"))
            assert body.get("status") == "published", f"Unexpected response: {body}"
            print(f"✅ E2E PASSED: Order {order.order_id} published to broker")
    except urllib.error.URLError as e:
        print(f"❌ E2E FAILED: Could not reach broker at {BROKER_URL}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_e2e_publish_order()
