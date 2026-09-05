//! Memory experience event producer for cross-language pipeline.
//!
//! Converts execution outcomes into EngineMessage envelopes and sends
//! them to the Go Message Broker via BrokerGateway.
//!
//! Governed by: contracts/schemas/memory/memory-experience-event-v1.json
//! Architecture Review: ARCH-REVIEW-002

use serde::Serialize;

use crate::gateway::{BrokerGateway, GatewayError};
use atlas_risk_engine::envelope::EngineMessage;

/// Outcome of an order execution attempt.
#[derive(Debug, Clone, PartialEq, Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionOutcome {
    pub order_id: String,
    pub symbol: String,
    pub side: String,
    pub quantity: f64,
    pub pnl: f64,
    pub status: String,
}

/// Outcome of a risk evaluation.
#[derive(Debug, Clone, PartialEq, Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RiskAssessmentEvent {
    pub assessment_type: String,
    pub result: String,
    pub circuit_breaker_state: String,
    pub risk_score: f64,
}

/// Record of an AI agent decision point.
#[derive(Debug, Clone, PartialEq, Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AgentDecisionEvent {
    pub decision_type: String,
    pub input_summary: String,
    pub output_action: String,
    pub confidence: f64,
}

/// Wraps a memory experience event payload into an EngineMessage envelope
/// compliant with engine-contract-v1.json and memory-experience-event-v1.json.
fn wrap_memory_event<T: Serialize>(payload: T) -> EngineMessage<T> {
    EngineMessage::new_risk_message(
        "memory.experience.v1",
        "memory-experience-event-v1",
        payload,
    )
}

/// Send an execution outcome event to the broker.
///
/// Returns Ok(()) on successful publish.
/// Returns Err(GatewayError) on serialization, HTTP, or broker rejection failure.
/// Failures are logged but do not affect order processing (fire-and-forget).
pub fn send_execution_outcome(
    gateway: &BrokerGateway,
    outcome: &ExecutionOutcome,
) -> Result<(), GatewayError> {
    let msg = wrap_memory_event(outcome.clone());
    let body = serde_json::to_vec(&msg)
        .map_err(|e| GatewayError::Serialization(e.to_string()))?;
    gateway.publish_raw(&body)
}

/// Send a risk assessment event to the broker.
pub fn send_risk_assessment(
    gateway: &BrokerGateway,
    assessment: &RiskAssessmentEvent,
) -> Result<(), GatewayError> {
    let msg = wrap_memory_event(assessment.clone());
    let body = serde_json::to_vec(&msg)
        .map_err(|e| GatewayError::Serialization(e.to_string()))?;
    gateway.publish_raw(&body)
}

/// Send an agent decision event to the broker.
pub fn send_agent_decision(
    gateway: &BrokerGateway,
    decision: &AgentDecisionEvent,
) -> Result<(), GatewayError> {
    let msg = wrap_memory_event(decision.clone());
    let body = serde_json::to_vec(&msg)
        .map_err(|e| GatewayError::Serialization(e.to_string()))?;
    gateway.publish_raw(&body)
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[test]
    fn execution_outcome_serializes_per_schema() {
        let outcome = ExecutionOutcome {
            order_id: Uuid::new_v4().to_string(),
            symbol: "BTCUSDT".to_string(),
            side: "buy".to_string(),
            quantity: 1.5,
            pnl: -150.0,
            status: "filled".to_string(),
        };
        let json = serde_json::to_value(&outcome);
        assert!(json.is_ok(), "ExecutionOutcome must serialize");
        let val = json.unwrap_or_default();
        assert_eq!(val["symbol"], "BTCUSDT");
        assert_eq!(val["side"], "buy");
        assert_eq!(val["status"], "filled");
        // deny_unknown_fields enforced at compile time
    }

    #[test]
    fn risk_assessment_serializes_per_schema() {
        let assessment = RiskAssessmentEvent {
            assessment_type: "position_limit".to_string(),
            result: "pass".to_string(),
            circuit_breaker_state: "normal".to_string(),
            risk_score: 42.0,
        };
        let json = serde_json::to_value(&assessment);
        assert!(json.is_ok(), "RiskAssessmentEvent must serialize");
        let val = json.unwrap_or_default();
        assert_eq!(val["result"], "pass");
        assert_eq!(val["risk_score"], 42.0);
    }

    #[test]
    fn agent_decision_serializes_per_schema() {
        let decision = AgentDecisionEvent {
            decision_type: "entry_signal".to_string(),
            input_summary: "RSI oversold on BTCUSDT".to_string(),
            output_action: "buy_limit".to_string(),
            confidence: 0.82,
        };
        let json = serde_json::to_value(&decision);
        assert!(json.is_ok(), "AgentDecisionEvent must serialize");
        let val = json.unwrap_or_default();
        assert_eq!(val["confidence"], 0.82);
    }

    #[test]
    fn wrap_memory_event_produces_valid_envelope() {
        let outcome = ExecutionOutcome {
            order_id: "test-id".to_string(),
            symbol: "ETHUSDT".to_string(),
            side: "sell".to_string(),
            quantity: 10.0,
            pnl: 500.0,
            status: "rejected".to_string(),
        };
        let msg = wrap_memory_event(outcome);
        assert_eq!(msg.contract_version, "1.0");
        assert_eq!(msg.message_type, "memory.experience.v1");
        assert_eq!(msg.source_engine, "rust_engine");
        assert!(!msg.timestamp.is_empty());
        assert_eq!(msg.metadata.specification_id, "memory-experience-event-v1");
        assert_eq!(msg.metadata.policy_version, "1.0");
        assert_eq!(msg.metadata.validation_status, "validated");
    }

    #[test]
    fn unknown_fields_rejected_at_deserialization() {
        let json = r#"{"order_id":"x","symbol":"BTC","side":"buy","quantity":1.0,"pnl":0.0,"status":"filled","bad_field":true}"#;
        let result: Result<ExecutionOutcome, _> = serde_json::from_str(json);
        assert!(result.is_err(), "unknown fields must be rejected");
    }
}
