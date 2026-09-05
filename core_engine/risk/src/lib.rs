//! Atlas Risk Engine
//!
//! Pre-execution risk gate for market strategy signals.
//! Fail-safe: when uncertain, deny.
//!
//! Governed by: docs/task_specs/risk_engine.md

#![forbid(unsafe_code)]
#![deny(clippy::all)]
#![deny(clippy::unwrap_used)]
#![deny(clippy::expect_used)]
#![deny(clippy::panic)]

pub mod assessment;
pub mod circuit_breaker;
pub mod envelope;
pub mod exposure_control;
pub mod kill_switch;
pub mod position_management;
pub mod types;

pub use assessment::{assess_order, RiskConfig};
pub use circuit_breaker::{CircuitBreaker, TradeResult};
pub use envelope::EngineMessage;
pub use kill_switch::KillSwitchManager;
pub use types::{
    CircuitBreakerConfig, HaltAction, KillSwitchActivation, KillSwitchScope, RiskAssessment,
};
