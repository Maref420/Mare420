//! Core types for the Risk Gate.
//! Governed by: contracts/schemas/risk/risk-assessment-v1.json

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

/// Risk assessment result. Mirrors risk-assessment-v1.json.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RiskAssessment {
    pub assessment_id: Uuid,
    pub order_id: Uuid,
    pub approved: bool,
    pub assessed_at: String,
    pub agent_id: String,
    pub checks_performed: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rejection_reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub risk_score: Option<f64>,
    #[serde(default)]
    pub metadata: HashMap<String, String>,
}

impl RiskAssessment {
    /// Validate assessment fields.
    pub fn validate(&self) -> Result<(), String> {
        if self.agent_id.is_empty() {
            return Err("agent_id must not be empty".to_string());
        }
        if self.assessed_at.is_empty() {
            return Err("assessed_at must not be empty".to_string());
        }
        if !self.approved && self.rejection_reason.is_none() {
            return Err("rejected assessment must have rejection_reason".to_string());
        }
        Ok(())
    }
}

/// Kill switch activation record.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct KillSwitchActivation {
    pub trigger_reason: String,
    pub activated_by: String,
    pub activated_at: String,
    pub scope: KillSwitchScope,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub auto_resume_at: Option<String>,
    #[serde(default)]
    pub metadata: HashMap<String, String>,
}

/// Kill switch scope.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum KillSwitchScope {
    EntireSystem,
    SingleAgent,
}

/// Circuit breaker configuration.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CircuitBreakerConfig {
    pub max_consecutive_losses: u32,
    pub max_daily_loss_pct: f64,
    pub cooldown_seconds: u64,
    pub halt_action: HaltAction,
}

impl CircuitBreakerConfig {
    pub fn validate(&self) -> Result<(), String> {
        if self.max_consecutive_losses == 0 {
            return Err("max_consecutive_losses must be > 0".to_string());
        }
        if self.max_daily_loss_pct < 0.0 {
            return Err("max_daily_loss_pct must be >= 0".to_string());
        }
        Ok(())
    }
}

/// Action to take when circuit breaker trips.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HaltAction {
    StopNewOrders,
    FullHalt,
}
