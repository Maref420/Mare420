//! Atlas Market Data Engine
//! Governed by: contracts/schemas/market/tick-data-v1.json
//! Policy: governance/policies/rust-policy.yaml

pub mod types;

// Re-export primary types for ergonomic access
pub use types::{TickDataV1, TickValidationError};
