use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;
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
    pub metadata: HashMap<String, serde_json::Value>,
}
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
    pub metadata: HashMap<String, serde_json::Value>,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", deny_unknown_fields)]
pub enum KillSwitchScope { SingleAgent, AllAgents, EntireSystem }
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CircuitBreakerConfig {
    pub max_consecutive_losses: u32,
    pub max_daily_loss_pct: f64,
    pub cooldown_seconds: u64,
    pub halt_action: HaltAction,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", deny_unknown_fields)]
pub enum HaltAction { CloseAll, StopNewOrders, FullHalt }
impl RiskAssessment {
    pub fn validate(&self) -> Result<(), String> {
        if self.agent_id.is_empty() {
            return Err("agent_id empty".into());
        }
        if self.checks_performed.is_empty() {
            return Err("checks_performed empty".into());
        }
        if !self.approved && self.rejection_reason.is_none() {
            return Err("rejection_reason required".into());
        }
        if let Some(s) = self.risk_score {
            if !(0.0..=1.0).contains(&s) {
                return Err(format!("risk_score {s} invalid"));
            }
        }
        Ok(())
    }
}
impl CircuitBreakerConfig {
    pub fn validate(&self) -> Result<(), String> {
        if self.max_consecutive_losses < 1 {
            return Err("max_consecutive_losses < 1".into());
        }
        if self.max_daily_loss_pct <= 0.0 || self.max_daily_loss_pct > 100.0 {
            return Err("max_daily_loss_pct invalid".into());
        }
        if self.cooldown_seconds < 60 {
            return Err("cooldown_seconds < 60".into());
        }
        Ok(())
    }
}
