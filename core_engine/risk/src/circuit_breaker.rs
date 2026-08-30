//! Circuit Breaker with trade-based tripping.
//! Governed by: risk/risk_engine/circuit_breaker/README.md

use crate::types::CircuitBreakerConfig;

/// Result of a single trade.
#[derive(Debug, Clone)]
pub struct TradeResult {
    pub pnl: f64,
}

/// Circuit breaker that trips on consecutive losses.
pub struct CircuitBreaker {
    config: CircuitBreakerConfig,
    consecutive_losses: u32,
    halted: bool,
}

impl CircuitBreaker {
    pub fn new(config: CircuitBreakerConfig) -> Self {
        Self {
            config,
            consecutive_losses: 0,
            halted: false,
        }
    }

    pub fn is_halted(&self) -> bool {
        self.halted
    }

    /// Record a trade result. Returns true if circuit breaker just tripped.
    pub fn record_trade(&mut self, result: &TradeResult) -> bool {
        if result.pnl < 0.0 {
            self.consecutive_losses += 1;
            if self.consecutive_losses >= self.config.max_consecutive_losses {
                self.halted = true;
                tracing::warn!(
                    consecutive = self.consecutive_losses,
                    "Circuit breaker TRIPPED"
                );
                return true;
            }
        } else {
            // Win resets consecutive loss counter
            self.consecutive_losses = 0;
        }
        false
    }
}
