//! Circuit Breaker with trade-based tripping.
//! Governed by: risk/risk_engine/circuit_breaker/README.md

use crate::types::CircuitBreakerConfig;

/// Result of a single trade.
#[derive(Debug, Clone)]
pub struct TradeResult {
    pub pnl: f64,
}

/// Circuit breaker that trips on consecutive losses or daily loss threshold.
pub struct CircuitBreaker {
    config: CircuitBreakerConfig,
    consecutive_losses: u32,
    daily_loss_accumulator: f64,
    halted: bool,
}

impl CircuitBreaker {
    pub fn new(config: CircuitBreakerConfig) -> Self {
        Self {
            config,
            consecutive_losses: 0,
            daily_loss_accumulator: 0.0,
            halted: false,
        }
    }

    pub fn is_halted(&self) -> bool {
        self.halted
    }

    /// Reset the circuit breaker to normal state.
    pub fn reset(&mut self) {
        self.consecutive_losses = 0;
        self.daily_loss_accumulator = 0.0;
        self.halted = false;
        tracing::info!("Circuit breaker RESET");
    }

    /// Record a trade result. Returns true if circuit breaker just tripped.
    pub fn record_trade(&mut self, result: &TradeResult) -> bool {
        if self.halted {
            return false;
        }

        if result.pnl < 0.0 {
            // Track consecutive losses
            self.consecutive_losses += 1;

            // Accumulate daily loss (as positive percentage-like value)
            self.daily_loss_accumulator += result.pnl.abs();

            // Check consecutive loss threshold
            if self.consecutive_losses >= self.config.max_consecutive_losses {
                self.halted = true;
                tracing::warn!(
                    consecutive = self.consecutive_losses,
                    "Circuit breaker TRIPPED (consecutive losses)"
                );
                return true;
            }

            // Check daily loss threshold
            if self.daily_loss_accumulator >= self.config.max_daily_loss_pct {
                self.halted = true;
                tracing::warn!(
                    daily_loss = self.daily_loss_accumulator,
                    max = self.config.max_daily_loss_pct,
                    "Circuit breaker TRIPPED (daily loss threshold)"
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
