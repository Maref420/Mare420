//! ╔═══════════════════════════════════════════════════════════╗
//! ║ MODULE: atlas-market-data                                ║
//! ║ OWNER: core_engine/market_data (Rust)                    ║
//! ║ CONTRACT: contracts/schemas/market/tick-data-v1.json     ║
//! ║ POLICY: governance/policies/rust-policy.yaml             ║
//! ║ STATUS: Production-Grade | Phase 1 Active                ║
//! ╠═══════════════════════════════════════════════════════════╣
//! ║ ⛔ DO NOT MODIFY WITHOUT:                                ║
//! ║   1. Checking contracts/schemas/market/tick-data-v1.json ║
//! ║   2. Running `make validate-market-data`                 ║
//! ║   3. Updating docs/decisions/ with ADR                   ║
//! ║ ⛔ NO FLOATS. NO PANIC. NO UNSAFE.                       ║
//! ╚═══════════════════════════════════════════════════════════╝
//! Atlas Market Data Engine
//! Governed by: contracts/schemas/market/tick-data-v1.json
//! Policy: governance/policies/rust-policy.yaml

pub mod types;

// Re-export primary types for ergonomic access
pub use types::{TickDataV1, TickValidationError};
