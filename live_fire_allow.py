#!/usr/bin/env python3
"""
Live Fire Allow Probe: Proves multi-agent feed when Policy allows.
Overrides adversarial survival to guarantee ALLOW for demonstration.
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
from intelligence.contracts.unified_decision_proposal import (
    AdversarialValidation,
    ConfidenceVector,
    DecisionProposal,
)
from intelligence.integration_bridge.nats_publisher import NATSPublisher
from intelligence.agent_control_plane.dispatcher.decision_dispatcher import dispatch_approved_decision
from intelligence.agents.strategy_agent_subscriber import StrategyAgentSubscriber
from intelligence.agents.risk_agent_subscriber import RiskAgentSubscriber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-40s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("LIVE_FIRE_ALLOW")


async def run_allow_probe() -> bool:
    start_time = time.perf_counter()
    trace_id = f"allow-{int(datetime.now(UTC).timestamp())}"

    logger.info("=" * 80)
    logger.info(f"ATLAS AI LIVE FIRE (ALLOW PATH) | Trace: {trace_id}")
    logger.info("=" * 80)

    # Start Subscribers
    strategy_sub = StrategyAgentSubscriber()
    risk_sub = RiskAgentSubscriber()
    await strategy_sub.start()
    await risk_sub.start()
    await asyncio.sleep(0.5)

    # Generate & Process Signal
    raw_signal = ForensicsSignal(
        symbol="ETHUSDT", raw_spread_bps=5, aqs_score=95,
        confidence=0.95, orderbook_imbalance=0.8, vpin_toxicity=0.05,
        spoofing_detected=False, trace_id=trace_id,
        timestamp_ns=int(datetime.now(UTC).timestamp() * 1e9),
        source_uri="live_allow://test",
    )
    agent = ResearchAgent(config={"aqs_threshold": 50, "toxicity_threshold": 0.5})
    decision = agent.process_signal(raw_json=raw_signal.model_dump_json(), trace_id=trace_id)
    proposal = translate_research_decision(decision)

    # Run Chaos but OVERRIDE survival to guarantee ALLOW for this probe
    chaos = ChaosEngine(seed=42)
    adv_report = chaos.stress_test(proposal)

    # Architectural override for demonstration purposes only
    override_adv = AdversarialValidation(
        tested_by_agent=adv_report.tested_by_agent,
        overfitting_detected=False,
        regime_failure_risk=0.1,
        data_leakage_risk=0.1,
        survival_score=0.85,  # Forced above 0.5 threshold
    )

    prop_dict = proposal.model_dump()
    prop_dict["adversarial_report"] = override_adv.model_dump()
    cv_dict = prop_dict["confidence_vector"]
    cv_dict["risk_compatibility"] = 0.9
    stressed_proposal = DecisionProposal(**prop_dict)

    # Policy Evaluation
    policy_decision, policy_reason = evaluate_proposal(stressed_proposal)
    logger.info(f"POLICY VERDICT: {policy_decision.value} ({policy_reason.value})")

    if policy_decision.value != "ALLOW":
        logger.error("UNEXPECTED: Policy did not return ALLOW. Probe aborted.")
        await strategy_sub.stop()
        await risk_sub.stop()
        return False

    # Publish & Dispatch
    publisher = NATSPublisher()
    await publisher.connect()

    dispatched = await dispatch_approved_decision(
        proposal=stressed_proposal,
        decision=policy_decision,
        publisher=publisher,
    )

    # Wait for subscribers to process
    await asyncio.sleep(1.0)

    # Cleanup
    await publisher.close()
    await strategy_sub.stop()
    await risk_sub.stop()

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info("=" * 80)
    logger.info(f"ALLOW PIPELINE COMPLETED | Dispatched: {dispatched} | Latency: {elapsed_ms:.2f}ms")
    logger.info("=" * 80)
    return dispatched


if __name__ == "__main__":
    success = asyncio.run(run_allow_probe())
    sys.exit(0 if success else 1)
