// Governance: Integration test file.
// clippy::expect_used and clippy::panic allowed ONLY in test scope.
// Production code remains strictly compliant per rust-policy.yaml.
// See ADR-2026-08-30-006.
#![allow(clippy::expect_used, clippy::panic)]

use atlas_risk_engine::types::RiskAssessment;
use atlas_risk_engine::envelope::EngineMessage;
use atlas_risk_engine::assessment::{assess_order, RiskConfig};
use uuid::Uuid;

/// Verify RiskAssessment round-trips through JSON without data loss.
/// This ensures Rust types stay in sync with risk-assessment-v1.json.
#[test]
fn risk_assessment_json_roundtrip() {
    let assessment = RiskAssessment {
        assessment_id: Uuid::new_v4(),
        order_id: Uuid::new_v4(),
        approved: true,
        assessed_at: "2026-08-30T00:00:00Z".to_string(),
        agent_id: "test-agent".to_string(),
        checks_performed: vec!["symbol_check".to_string()],
        rejection_reason: None,
        risk_score: Some(0.5),
        metadata: std::collections::HashMap::new(),
    };
    let json = serde_json::to_string(&assessment).expect("serialize failed");
    let deserialized: RiskAssessment = serde_json::from_str(&json).expect("deserialize failed");
    assert_eq!(assessment, deserialized);
    assert!(deserialized.validate().is_ok());
}

/// Verify rejected assessment includes rejection_reason.
#[test]
fn rejected_assessment_has_reason() {
    let assessment = RiskAssessment {
        assessment_id: Uuid::new_v4(),
        order_id: Uuid::new_v4(),
        approved: false,
        assessed_at: "2026-08-30T00:00:00Z".to_string(),
        agent_id: "test-agent".to_string(),
        checks_performed: vec!["quantity_check".to_string()],
        rejection_reason: Some("quantity exceeds limit".to_string()),
        risk_score: None,
        metadata: std::collections::HashMap::new(),
    };
    assert!(assessment.validate().is_ok());
    let json = serde_json::to_string(&assessment).expect("serialize failed");
    assert!(json.contains("rejection_reason"));
}

/// Verify unknown fields are rejected (deny_unknown_fields).
#[test]
fn unknown_fields_rejected() {
    let json = r#"{"assessment_id":"00000000-0000-0000-0000-000000000000","order_id":"00000000-0000-0000-0000-000000000000","approved":true,"assessed_at":"2026-01-01T00:00:00Z","agent_id":"a","checks_performed":["x"],"unknown_field":true}"#;
    let result: Result<RiskAssessment, _> = serde_json::from_str(json);
    assert!(result.is_err(), "unknown fields must be rejected");
}

/// Verify assess_order produces valid assessment for good order.
#[test]
fn assess_order_approved() {
    let config = RiskConfig {
        max_order_quantity: 100.0,
        allowed_symbols: vec!["BTCUSDT".to_string()],
        require_risk_score: true,
    };
    let result = assess_order(Uuid::new_v4(), "agent-1", "BTCUSDT", 10.0, &config);
    assert!(result.approved);
    assert!(result.rejection_reason.is_none());
    assert!(result.risk_score.is_some());
    assert!(result.validate().is_ok());
}

/// Verify assess_order rejects disallowed symbol.
#[test]
fn assess_order_rejected_symbol() {
    let config = RiskConfig {
        max_order_quantity: 100.0,
        allowed_symbols: vec!["BTCUSDT".to_string()],
        require_risk_score: false,
    };
    let result = assess_order(Uuid::new_v4(), "agent-1", "ETHUSDT", 10.0, &config);
    assert!(!result.approved);
    assert!(result.rejection_reason.is_some());
    assert!(result.validate().is_ok());
}

/// Verify EngineMessage envelope wraps assessment correctly.
#[test]
fn envelope_wraps_assessment() {
    let config = RiskConfig {
        max_order_quantity: 100.0,
        allowed_symbols: vec![],
        require_risk_score: false,
    };
    let assessment = assess_order(Uuid::new_v4(), "agent-1", "BTCUSDT", 5.0, &config);
    let msg = EngineMessage::new_risk_message("risk.assessment.v1", "risk-assessment-v1", assessment);
    assert_eq!(msg.contract_version, "1.0");
    assert_eq!(msg.source_engine, "rust_engine");
    assert_eq!(msg.metadata.owner, "Risk Engine");
    let json = serde_json::to_string(&msg).expect("envelope serialize failed");
    assert!(json.contains("risk.assessment.v1"));
}

/// Verify KillSwitchActivation round-trips through JSON.
#[test]
fn kill_switch_json_roundtrip() {
    use atlas_risk_engine::types::{KillSwitchActivation, KillSwitchScope};
    let activation = KillSwitchActivation {
        trigger_reason: "excessive loss".to_string(),
        activated_by: "risk-engine".to_string(),
        activated_at: "2026-08-30T00:00:00Z".to_string(),
        scope: KillSwitchScope::EntireSystem,
        auto_resume_at: None,
        metadata: std::collections::HashMap::new(),
    };
    let json = serde_json::to_string(&activation).expect("serialize failed");
    let deserialized: KillSwitchActivation = serde_json::from_str(&json).expect("deserialize failed");
    assert_eq!(activation, deserialized);
}

/// Verify KillSwitchManager state transitions.
#[test]
fn kill_switch_state_transitions() {
    use atlas_risk_engine::kill_switch::KillSwitchManager;
    use atlas_risk_engine::types::KillSwitchScope;
    let mut mgr = KillSwitchManager::new();
    assert!(!mgr.is_active());
    assert!(mgr.current_activation().is_none());
    let activation = mgr.activate(
        "test trigger".to_string(),
        "test-agent".to_string(),
        KillSwitchScope::SingleAgent,
    );
    assert!(mgr.is_active());
    assert_eq!(activation.trigger_reason, "test trigger");
    assert_eq!(activation.scope, KillSwitchScope::SingleAgent);
    let prev = mgr.deactivate("admin");
    assert!(prev.is_some());
    assert!(!mgr.is_active());
    assert!(mgr.current_activation().is_none());
}

/// Verify deactivate on inactive returns None.
#[test]
fn kill_switch_deactivate_when_inactive() {
    use atlas_risk_engine::kill_switch::KillSwitchManager;
    let mut mgr = KillSwitchManager::new();
    assert!(mgr.deactivate("admin").is_none());
}

/// Verify unknown fields rejected in KillSwitchActivation.
#[test]
fn kill_switch_unknown_fields_rejected() {
    use atlas_risk_engine::types::KillSwitchActivation;
    let json = r#"{"trigger_reason":"x","activated_by":"y","activated_at":"2026-01-01T00:00:00Z","scope":"entire_system","bad_field":true}"#;
    let result: Result<KillSwitchActivation, _> = serde_json::from_str(json);
    assert!(result.is_err(), "unknown fields must be rejected");
}
#[test]
fn circuit_breaker_json_roundtrip() {
    use atlas_risk_engine::types::{CircuitBreakerConfig, HaltAction};
    let config = CircuitBreakerConfig {
        max_consecutive_losses: 5,
        max_daily_loss_pct: 10.0,
        cooldown_seconds: 300,
        halt_action: HaltAction::StopNewOrders,
    };
    let json = serde_json::to_string(&config).expect("serialize failed");
    let deserialized: CircuitBreakerConfig = serde_json::from_str(&json).expect("deserialize failed");
    assert_eq!(config, deserialized);
    assert!(deserialized.validate().is_ok());
}
#[test]
fn circuit_breaker_trips_on_consecutive_losses() {
    use atlas_risk_engine::circuit_breaker::{CircuitBreaker, TradeResult};
    use atlas_risk_engine::types::{CircuitBreakerConfig, HaltAction};
    let config = CircuitBreakerConfig { max_consecutive_losses: 3, max_daily_loss_pct: 100.0, cooldown_seconds: 60, halt_action: HaltAction::FullHalt };
    let mut cb = CircuitBreaker::new(config);
    assert!(!cb.is_halted());
    cb.record_trade(&TradeResult { pnl: -1.0 });
    cb.record_trade(&TradeResult { pnl: -1.0 });
    assert!(!cb.is_halted());
    let tripped = cb.record_trade(&TradeResult { pnl: -1.0 });
    assert!(tripped);
    assert!(cb.is_halted());
}
#[test]
fn circuit_breaker_resets_consecutive_on_win() {
    use atlas_risk_engine::circuit_breaker::{CircuitBreaker, TradeResult};
    use atlas_risk_engine::types::{CircuitBreakerConfig, HaltAction};
    let config = CircuitBreakerConfig { max_consecutive_losses: 3, max_daily_loss_pct: 100.0, cooldown_seconds: 60, halt_action: HaltAction::FullHalt };
    let mut cb = CircuitBreaker::new(config);
    cb.record_trade(&TradeResult { pnl: -1.0 });
    cb.record_trade(&TradeResult { pnl: -1.0 });
    cb.record_trade(&TradeResult { pnl: 5.0 });
    assert!(!cb.is_halted());
}
#[test]
fn circuit_breaker_unknown_fields_rejected() {
    use atlas_risk_engine::types::CircuitBreakerConfig;
    let json = r#"{"max_consecutive_losses":5,"max_daily_loss_pct":10.0,"cooldown_seconds":300,"halt_action":"full_halt","bad":true}"#;
    let result: Result<CircuitBreakerConfig, _> = serde_json::from_str(json);
    assert!(result.is_err(), "unknown fields must be rejected");
}