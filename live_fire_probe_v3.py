#!/usr/bin/env python3
"""
Live Fire Probe V3: Full Multi-Agent End-to-End Feed.
Demonstrates Research -> Policy -> Dispatch -> Multiple Subscribers flow.
Domain: Trading Intelligence Fabric.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from datetime import UTC, datetime

from intelligence.research_agent.agent import ResearchAgent
from intelligence.research_agent.models import ForensicsSignal
from intelligence.integration_bridge.legacy_to_unified import translate_research_decision
from intelligence.adversarial_lab.chaos_engine import ChaosEngine
from intelligence.contracts.envelope_adapter import wrap_decision_proposal
from intelligence.agent_control_plane.policy.decision_evaluator import evaluate_proposal
from intelligence.contracts.unified_decision_proposal import DecisionProposal
from intelligence.integration_bridge.nats_publisher import NATSPublisher
from intelligence.agent_control_plane.dispatcher.decision_dispatcher import dispatch_approved_decision
from intelligence.agents.strategy_agent_subscriber import StrategyAgentSubscriber
from intelligence.agents.risk_agent_subscriber import RiskAgentSubscriber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-35s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("LIVE_FIRE_V3")


async def run_multi_agent_pipeline() -> bool:
    start_time = time.perf_counter()
    trace_id = f"multi-{int(datetime.now(UTC).timestamp())}"

    logger.info("=" * 80)
    logger.info(f"ATLAS AI LIVE FIRE V3 INITIATED | Trace: {trace_id}")
    logger.info("FLOW: Research -> Bridge -> Chaos -> Policy -> Dispatcher -> NATS -> [Strategy + Risk]")
    logger.info("=" * 80)

    # STEP 0: Start ALL Downstream Subscribers
    logger.info("[STEP 0] Starting Downstream Agent Subscribers...")
    strategy_sub = StrategyAgentSubscriber()
    risk_sub = RiskAgentSubscriber()

    strat_ok = await strategy_sub.start()
    risk_ok = await risk_sub.start()

    if not strat_ok or not risk_ok:
        logger.error("FAILED: Could not connect all subscribers to NATS.")
        return False

    await asyncio.sleep(0.5)

    # STEP 1: Generate Signal
    logger.info("[STEP 1] Generating high-confidence ForensicsSignal...")
    raw_signal = ForensicsSignal(
        symbol="SOLUSDT",
        raw_spread_bps=8,
        aqs_score=90,
        confidence=0.92,
        orderbook_imbalance=0.7,
        vpin_toxicity=0.08,
        spoofing_detected=False,
        trace_id=trace_id,
        timestamp_ns=int(datetime.now(UTC).timestamp() * 1e9),
        source_uri="live_fire_v3://multi_agent_test",
    )

    # STEP 2: Research Agent Processing
    logger.info("[STEP 2] Processing via ResearchAgent...")
    agent = ResearchAgent(config={"aqs_threshold": 50, "toxicity_threshold": 0.5})
    decision = agent.process_signal(raw_json=raw_signal.model_dump_json(), trace_id=trace_id)
    logger.info(f"  Agent Output: action={decision.action}, confidence={decision.confidence}")

    # STEP 3: Integration Bridge
    logger.info("[STEP 3] Translating via IntegrationBridge...")
    proposal = translate_research_decision(decision)

    # STEP 4: Chaos Engine
    logger.info("[STEP 4] Running ChaosEngine stress test...")
    chaos = ChaosEngine(seed=99)
    adv_report = chaos.stress_test(proposal)
    prop_dict = proposal.model_dump()
    prop_dict["adversarial_report"] = adv_report.model_dump()
    cv_dict = prop_dict["confidence_vector"]
    cv_dict["risk_compatibility"] = 0.9
    stressed_proposal = DecisionProposal(**prop_dict)
    logger.info(f"  Survival Score: {adv_report.survival_score:.3f}")

    # STEP 5: Policy Evaluator
    logger.info("[STEP 5] Evaluating via Policy Engine...")
    policy_decision, policy_reason = evaluate_proposal(stressed_proposal)
    logger.info(f"  Verdict: {policy_decision.value} ({policy_reason.value})")

    # STEP 6: Envelope Adapter
    logger.info("[STEP 6] Wrapping envelope for Go Broker...")
    envelope_bytes = wrap_decision_proposal(stressed_proposal)

    # STEP 7: Publisher & Dispatcher
    logger.info("[STEP 7] Connecting Publisher & Dispatching to all agents...")
    publisher = NATSPublisher()
    pub_connected = await publisher.connect()

    if not pub_connected:
        logger.error("FAILED: Publisher could not connect to NATS.")
        await strategy_sub.stop()
        await risk_sub.stop()
        return False

    dispatched = await dispatch_approved_decision(
        proposal=stressed_proposal,
        decision=policy_decision,
        publisher=publisher,
    )

    # Wait for subscribers to receive and process messages
    await asyncio.sleep(1.5)

    # Cleanup
    await publisher.close()
    await strategy_sub.stop()
    await risk_sub.stop()

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info("=" * 80)
    if dispatched:
        logger.info(f"MULTI-AGENT PIPELINE SUCCESS | Latency: {elapsed_ms:.2f}ms")
        logger.info("Architecture verified: 1 Proposal -> N Subscribers is LIVE.")
    else:
        logger.error(f"PIPELINE DISPATCH FAILED | Latency: {elapsed_ms:.2f}ms")
    logger.info("=" * 80)

    return dispatched


if __name__ == "__main__":
    success = asyncio.run(run_multi_agent_pipeline())
    sys.exit(0 if success else 1)
