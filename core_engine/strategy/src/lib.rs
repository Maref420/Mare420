//! Atlas Strategy Engine
//!
//! Architecture (A+ Pattern):
//! - `contract_types`: 1:1 mapping of strategy-signal-event-v1 JSON Schema.
//!   Used at cross-language boundaries. No business logic.
//! - `domain_types`: Internal execution types with scaled integers (ADR-2026-08-30-004).
//!   Never exposed outside Rust boundary.
//! - `conversions`: Bridge between contract ↔ domain via TryFrom.
//!
//! Governed by: contracts/schemas/strategy/strategy-signal-event-v1.schema.json
//! Policy: governance/policies/rust-policy.yaml

pub mod contract_types;
pub mod conversions;
pub mod domain_types;

// Re-export primary types for ergonomic use
pub use contract_types::{
    ContractValidationError, Direction, MarketRegime,
    Signal as ContractSignal, StrategySignalEventV1 as ContractEvent,
};
pub use conversions::ConversionError;
pub use domain_types::{SignalType, StrategySignalEventV1 as DomainEvent, StrategyValidationError};
