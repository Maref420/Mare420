#!/usr/bin/env python3
"""
Live Fire Probe: End-to-End Runtime Telemetry WITH Physical Transport.
Injects a signal, processes through all 6 governance layers,
and physically publishes the envelope to NATS for Go Broker consumption.
Domain: Trading Intelligence Fabric.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from datetime import UTC, datetime

from intelligence.research_agent.agent import ResearchAgent
from intelligence.research_agent.models import ForensicsSignal
from intelligence.integration_bridge.legacy_to_unified import translate_research_decision
from intelligence.adversarial_lab.chaos_engine import ChaosEngine
from intelligence.contracts.envelope_adapter import wrap_decision_proposal
from intelligence.agent_control_plane.policy.decision_evaluator import (
    evaluate_proposal,
    PolicyDecision,
)
from intelligence.contracts.unified_decision_proposal import DecisionProposal
from intelligence.integration_bridge.nats_publisher import NATSPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("LIVE_FIRE_PROBE")


async def run_live_fire_probe() -> bool:
    """Execute full pipeline including physical NATS transport."""
    start_time = time.perf_counter()
    trace_id = f"fire-{int(datetime.now(UTC).timestamp())}"

    logger.info("=" * 70)
    logger.info(f"ATLAS AI LIVE FIRE PROBE INITIATED | Trace: {trace_id}")
    logger.info("DOMAIN: Trading Intelligence Fabric (Physical Transport)")
    logger.info("=" * 70)

    # STEP 1-6: In-Memory Governance Pipeline
    logger.info("[STEPS 1-6] Executing in-memory governance pipeline...")
    try:
        raw_signal = ForensicsSignal(
            symbol="BTCUSDT",
            raw_spread_bps=15,
            aqs_score=85,
            confidence=0.82,
            orderbook_imbalance=0.4,
            vpin_toxicity=0.12,
            spoofing_detected=False,
            trace_id=trace_id,
            timestamp_ns=int(datetime.now(UTC).timestamp() * 1e9),
            source_uri="live_fire://transport_test",
        )
        agent = ResearchAgent(config={"aqs_threshold": 50, "toxicity_threshold": 0.5})
        decision = agent.process_signal(
            raw_json=raw_signal.model_dump_json(), trace_id=trace_id
        )
        proposal = translate_research_decision(decision)

        chaos = ChaosEngine(seed=42)
        adv_report = chaos.stress_test(proposal)
        prop_dict = proposal.model_dump()
        prop_dict["adversarial_report"] = adv_report.model_dump()
        stressed_proposal = DecisionProposal(**prop_dict)

        envelope_bytes = wrap_decision_proposal(stressed_proposal)
        policy_decision, policy_reason = evaluate_proposal(stressed_proposal)

        logger.info(f"  Pipeline Verdict: {policy_decision.value} ({policy_reason.value})")
    except Exception as e:
        logger.error(f"  FAILED: Pipeline error: {e}")
        return False

    # STEP 7: Physical Transport via NATS
    logger.info("[STEP 7] Publishing envelope to NATS Event Bus...")
    publisher = NATSPublisher()
    connected = await publisher.connect()

    if not connected:
        logger.warning("  SKIPPED: NATS unavailable. Envelope generated but not transported.")
        logger.warning("  To enable transport, ensure atlas-nats container is running.")
        await publisher.close()
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"LIVE FIRE COMPLETED (LOCAL ONLY) | Latency: {elapsed_ms:.2f}ms")
        return True

    published = await publisher.publish(envelope_bytes)
    await publisher.close()

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info("=" * 70)
    if published:
        logger.info(f"LIVE FIRE SUCCESS | Envelope delivered to Go Broker | Latency: {elapsed_ms:.2f}ms")
    else:
        logger.error(f"LIVE FIRE TRANSPORT FAILED | Pipeline OK but publish failed | Latency: {elapsed_ms:.2f}ms")
    logger.info("=" * 70)

    return published


if __name__ == "__main__":
    success = asyncio.run(run_live_fire_probe())
    sys.exit(0 if success else 1)
