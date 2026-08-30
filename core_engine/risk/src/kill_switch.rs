//! Kill Switch Manager.
//! Governed by: risk/risk_engine/kill_switch/README.md

use crate::types::{KillSwitchActivation, KillSwitchScope};

/// Manages kill switch state with full audit trail.
pub struct KillSwitchManager {
    activation: Option<KillSwitchActivation>,
}

impl KillSwitchManager {
    pub fn new() -> Self {
        Self { activation: None }
    }

    pub fn is_active(&self) -> bool {
        self.activation.is_some()
    }

    pub fn current_activation(&self) -> Option<&KillSwitchActivation> {
        self.activation.as_ref()
    }

    /// Activate the kill switch. Returns owned activation record.
    pub fn activate(
        &mut self,
        trigger_reason: String,
        activated_by: String,
        scope: KillSwitchScope,
    ) -> KillSwitchActivation {
        let now = chrono::Utc::now().to_rfc3339();
        let record = KillSwitchActivation {
            trigger_reason,
            activated_by,
            activated_at: now,
            scope,
            auto_resume_at: None,
            metadata: std::collections::HashMap::new(),
        };
        tracing::error!("KILL SWITCH ACTIVATED: {:?}", record);
        self.activation = Some(record.clone());
        record
    }

    /// Deactivate the kill switch. Returns previous activation if any.
    pub fn deactivate(&mut self, deactivated_by: &str) -> Option<KillSwitchActivation> {
        let prev = self.activation.take();
        if prev.is_some() {
            tracing::info!("Kill switch deactivated by {deactivated_by}");
        }
        prev
    }
}

impl Default for KillSwitchManager {
    fn default() -> Self {
        Self::new()
    }
}
