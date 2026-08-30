use crate::types::{KillSwitchActivation, KillSwitchScope};
use std::collections::HashMap;

/// Current state of the kill switch.
#[derive(Debug, Clone, PartialEq)]
pub enum KillSwitchState {
    Inactive,
    Active(KillSwitchActivation),
}

/// Manages kill switch lifecycle per kill-switch-v1.json.
/// Deactivation requires manual approval (enforced by caller).
#[derive(Debug, Clone)]
pub struct KillSwitchManager {
    state: KillSwitchState,
}

impl KillSwitchManager {
    pub fn new() -> Self {
        Self { state: KillSwitchState::Inactive }
    }

    pub fn is_active(&self) -> bool {
        matches!(self.state, KillSwitchState::Active(_))
    }

    pub fn current_activation(&self) -> Option<&KillSwitchActivation> {
        match &self.state {
            KillSwitchState::Active(a) => Some(a),
            KillSwitchState::Inactive => None,
        }
    }

    /// Activate the kill switch. Returns the activation record for audit.
    pub fn activate(
        &mut self,
        trigger_reason: String,
        activated_by: String,
        scope: KillSwitchScope,
    ) -> KillSwitchActivation {
        let activation = KillSwitchActivation {
            trigger_reason,
            activated_by,
            activated_at: chrono::Utc::now().to_rfc3339(),
            scope,
            auto_resume_at: None,
            metadata: HashMap::new(),
        };
        self.state = KillSwitchState::Active(activation.clone());
        tracing::warn!("Kill switch ACTIVATED: {:?}", activation.trigger_reason);
        activation
    }

    /// Deactivate the kill switch. Caller must verify manual approval.
    /// Returns the previous activation record for audit.
    pub fn deactivate(&mut self, deactivated_by: &str) -> Option<KillSwitchActivation> {
        match self.state.clone() {
            KillSwitchState::Active(prev) => {
                tracing::info!("Kill switch DEACTIVATED by {deactivated_by}");
                self.state = KillSwitchState::Inactive;
                Some(prev)
            }
            KillSwitchState::Inactive => None,
        }
    }
}
