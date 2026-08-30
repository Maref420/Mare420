use crate::types::{CircuitBreakerConfig, HaltAction};
/// Tracks consecutive losses and daily loss percentage.
/// Derived from circuit-breaker-v1.json.
#[derive(Debug, Clone)]
pub struct TradeResult {
    pub pnl: f64,
}
#[derive(Debug, Clone, PartialEq)]
pub enum BreakerState {
    Normal,
    Tripped { halt_action: HaltAction, tripped_at: String },
    Cooldown { resume_at: String },
}
#[derive(Debug, Clone)]
pub struct CircuitBreaker {
    config: CircuitBreakerConfig,
    state: BreakerState,
    consecutive_losses: u32,
    daily_loss_pct: f64,
}
impl CircuitBreaker {
    pub fn new(config: CircuitBreakerConfig) -> Self {
        Self { config, state: BreakerState::Normal, consecutive_losses: 0, daily_loss_pct: 0.0 }
    }
    pub fn is_halted(&self) -> bool {
        matches!(self.state, BreakerState::Tripped { .. })
    }
    pub fn halt_action(&self) -> Option<HaltAction> {
        match &self.state {
            BreakerState::Tripped { halt_action, .. } => Some(halt_action.clone()),
            _ => None,
        }
    }
    /// Record a trade result. Returns true if breaker just tripped.
    pub fn record_trade(&mut self, result: &TradeResult) -> bool {
        if result.pnl < 0.0 {
            self.consecutive_losses += 1;
            self.daily_loss_pct += result.pnl.abs();
        } else {
            self.consecutive_losses = 0;
        }
        let should_trip = self.consecutive_losses >= self.config.max_consecutive_losses
            || self.daily_loss_pct >= self.config.max_daily_loss_pct;
        if should_trip && !self.is_halted() {
            self.state = BreakerState::Tripped {
                halt_action: self.config.halt_action.clone(),
                tripped_at: chrono::Utc::now().to_rfc3339(),
            };
            tracing::warn!("Circuit breaker TRIPPED: {:?}", self.config.halt_action);
            return true;
        }
        false
    }
    /// Reset breaker after cooldown. Caller must verify cooldown elapsed.
    pub fn reset(&mut self) {
        self.state = BreakerState::Normal;
        self.consecutive_losses = 0;
        self.daily_loss_pct = 0.0;
        tracing::info!("Circuit breaker RESET");
    }
}
