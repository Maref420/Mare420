"""PRODUCTION VALIDATION: Measure real E2E latency Python → Go Broker.
Establishes baseline for future performance regression detection."""
import json
import time
import urllib.request
import subprocess
import sys
import os
from atlas_agent.models import Order, OrderSide, OrderType, EngineMessage

BROKER_URL = "http://localhost:8090/publish"
HEALTH_URL = "http://localhost:8090/health"

def wait_for_broker(timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(HEALTH_URL, timeout=1)
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False

def test_e2e_latency_baseline():
    # Start broker
    broker_bin = "/tmp/broker"
    if not os.path.exists(broker_bin):
        print("⚠️ Broker binary not found at /tmp/broker, skipping latency test")
        return
    proc = subprocess.Popen([broker_bin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for_broker():
            print("❌ Broker did not become healthy within timeout")
            sys.exit(1)

        order = Order(symbol="BTCUSDT", side=OrderSide.BUY, quantity=1.0,
                      order_type=OrderType.MARKET, agent_id="latency-test")
        msg = EngineMessage.wrap_order(order, "latency-test")
        payload = msg.model_dump_json().encode("utf-8")

        latencies = []
        for i in range(100):
            req = urllib.request.Request(BROKER_URL, data=payload,
                headers={"Content-Type": "application/json"}, method="POST")
            start = time.perf_counter()
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        avg = sum(latencies) / len(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        print(f"✅ Latency baseline: avg={avg:.2f}ms p99={p99:.2f}ms (100 requests)")
        # Sanity check: p99 should be under 50ms for local HTTP
        assert p99 < 50.0, f"p99 latency {p99:.2f}ms exceeds 50ms threshold"
    finally:
        proc.terminate()
        proc.wait(timeout=5)
