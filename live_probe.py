#!/usr/bin/env python3
"""
Live Probe: End-to-End Runtime Telemetry for Atlas AI Trading Fabric.
Injects a valid signal into ResearchAgent and traces it through
the entire Phase 1-6 governance pipeline in real-time.
Contains ZERO side effects. No external network calls.
Domain: Trading Intelligence Fabric (Independent from CodeGen CLI).
"""
from __future__ import annotations

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("LIVE_PROBE")


def run_live_probe() -> bool:
    """Execute full pipeline trace with structured logging."""
    start_time = time.perf_counter()
    trace_id = f"probe-{int(datetime.now(UTC).timestamp())}"
    
    logger.info("=" * 70)
    logger.info(f"ATLAS AI LIVE PROBE INITIATED | Trace: {trace_id}")
    logger.info("DOMAIN: Trading Intelligence Fabric (Isolated)")
    logger.info("=" * 70)

    # STEP 1: Generate Valid Forensics Signal (ADR-006 Compliant)
    logger.info("[STEP 1] Generating valid ForensicsSignal...")
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
            source_uri="live_probe://telemetry_test",
        )
        raw_json = raw_signal.model_dump_json()
        logger.info(f"  SUCCESS: Signal generated. Size: {len(raw_json)} bytes")
    except Exception as e:
        logger.error(f"  FAILED: Signal generation error: {e}")
        return False

    # STEP 2: Process through ResearchAgent
    logger.info("[STEP 2] Feeding signal to ResearchAgent...")
    try:
        agent_config = {"aqs_threshold": 50, "toxicity_threshold": 0.5}
        agent = ResearchAgent(config=agent_config)
        decision = agent.process_signal(raw_json=raw_json, trace_id=trace_id)
        logger.info("  SUCCESS: Agent produced decision.")
        logger.info(f"     Action: {decision.action} | Confidence: {decision.confidence}")
    except Exception as e:
        logger.error(f"  FAILED: Agent processing error: {e}")
        return False

    # STEP 3: Integration Bridge Translation
    logger.info("[STEP 3] Translating via IntegrationBridge...")
    try:
        proposal = translate_research_decision(decision)
        logger.info("  SUCCESS: Translated to DecisionProposal.")
        logger.info(f"     Epistemic: {proposal.epistemic_status.value}")
        logger.info(f"     Evidence Count: {len(proposal.required_evidence)}")
    except Exception as e:
        logger.error(f"  FAILED: Bridge translation error: {e}")
        return False

    # STEP 4: Chaos Engine Stress Test
    logger.info("[STEP 4] Running ChaosEngine stress test...")
    try:
        chaos = ChaosEngine(seed=42)
        adv_report = chaos.stress_test(proposal)
        
        prop_dict = proposal.model_dump()
        prop_dict["adversarial_report"] = adv_report.model_dump()
        stressed_proposal = DecisionProposal(**prop_dict)
        
        logger.info("  SUCCESS: Chaos evaluation completed.")
        logger.info(f"     Survival Score: {adv_report.survival_score:.3f}")
        logger.info(f"     Overfitting: {adv_report.overfitting_detected}")
    except Exception as e:
        logger.error(f"  FAILED: Chaos engine error: {e}")
        return False

    # STEP 5: Envelope Adapter (Go Broker Ready)
    logger.info("[STEP 5] Wrapping in Go-Compatible Envelope...")
    try:
        envelope_bytes = wrap_decision_proposal(stressed_proposal)
        envelope_dict = json.loads(envelope_bytes.decode("utf-8"))
        logger.info("  SUCCESS: Envelope ready for NATS.")
        logger.info(f"     Message Type: {envelope_dict['message_type']}")
        logger.info(f"     Payload Size: {len(envelope_bytes)} bytes")
    except Exception as e:
        logger.error(f"  FAILED: Envelope adapter error: {e}")
        return False

    # STEP 6: Policy Evaluator Final Gate
    logger.info("[STEP 6] Evaluating via Deterministic Policy Engine...")
    try:
        policy_decision, policy_reason = evaluate_proposal(stressed_proposal)
        logger.info("  SUCCESS: Policy evaluation completed.")
        logger.info(f"     DECISION: {policy_decision.value}")
        logger.info(f"     REASON: {policy_reason.value}")
    except Exception as e:
        logger.error(f"  FAILED: Policy evaluator error: {e}")
        return False

    # TELEMETRY SUMMARY
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info("=" * 70)
    logger.info(f"LIVE PROBE COMPLETED | Total Latency: {elapsed_ms:.2f}ms")
    logger.info(f"FINAL VERDICT: {policy_decision.value} ({policy_reason.value})")
    logger.info("=" * 70)
    
    return True


if __name__ == "__main__":
    success = run_live_probe()
    sys.exit(0 if success else 1)
