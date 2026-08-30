//! Production integration test: Rust memory_events → real Go Broker.
//! Requires broker running on localhost:8090.
//! Run manually: cargo test --test prod_memory_pipeline -- --ignored

use atlas_execution_engine::gateway::BrokerGateway;
use atlas_execution_engine::memory_events::{
    self, ExecutionOutcome, RiskAssessmentEvent, AgentDecisionEvent,
};

const BROKER_URL: &str = "http://localhost:8090";

fn broker_available() -> bool {
    ureq::get(&format!("{}/health", BROKER_URL))
        .call()
        .map(|r| r.status() == 200)
        .unwrap_or(false)
}

#[test]
#[ignore] // requires running broker
fn rust_execution_outcome_reaches_broker() {
    if !broker_available() {
        panic!("Broker not available at {}", BROKER_URL);
    }
    let gw = BrokerGateway::new(BROKER_URL);
    let outcome = ExecutionOutcome {
        order_id: "rust-real-001".to_string(),
        symbol: "BTCUSDT".to_string(),
        side: "buy".to_string(),
        quantity: 3.0,
        pnl: -75.0,
        status: "filled".to_string(),
    };
    let result = memory_events::send_execution_outcome(&gw, &outcome);
    assert!(result.is_ok(), "Failed to send execution outcome: {:?}", result.err());
}

#[test]
#[ignore] // requires running broker
fn rust_risk_assessment_reaches_broker() {
    if !broker_available() {
        panic!("Broker not available at {}", BROKER_URL);
    }
    let gw = BrokerGateway::new(BROKER_URL);
    let assessment = RiskAssessmentEvent {
        assessment_type: "position_limit".to_string(),
        result: "warn".to_string(),
        circuit_breaker_state: "normal".to_string(),
        risk_score: 65.0,
    };
    let result = memory_events::send_risk_assessment(&gw, &assessment);
    assert!(result.is_ok(), "Failed to send risk assessment: {:?}", result.err());
}

#[test]
#[ignore] // requires running broker
fn rust_agent_decision_reaches_broker() {
    if !broker_available() {
        panic!("Broker not available at {}", BROKER_URL);
    }
    let gw = BrokerGateway::new(BROKER_URL);
    let decision = AgentDecisionEvent {
        decision_type: "exit_signal".to_string(),
        input_summary: "Take profit target reached".to_string(),
        output_action: "sell_market".to_string(),
        confidence: 0.91,
    };
    let result = memory_events::send_agent_decision(&gw, &decision);
    assert!(result.is_ok(), "Failed to send agent decision: {:?}", result.err());
}
