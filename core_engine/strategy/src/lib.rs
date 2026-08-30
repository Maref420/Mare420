//! Atlas Strategy Engine
//! Governed by: contracts/schemas/events/strategy-signal-event-v1.json
//! Policy: governance/policies/rust-policy.yaml

pub mod types;

pub use types::{StrategySignalEventV1, SignalType, StrategyValidationError};
