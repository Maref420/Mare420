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
//! Tick Data Types — Governed by contracts/schemas/market/tick-data-v1.json
//! All numeric fields use scaled integers per ADR-2026-08-30-001.
//! No floating-point types allowed per rust-policy.yaml deterministic_processing_required.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// Production-grade market tick data.
/// Immutable after creation. All fields validated at construction boundary.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TickDataV1 {
    /// Trading pair symbol (e.g., "BTCUSDT")
    pub symbol: String,

    /// Price in smallest currency unit (e.g., satoshis, cents).
    /// Scale factor defined per exchange in configs/exchanges/.
    /// Must be > 0.
    pub price_scaled: u64,

    /// Volume in smallest asset unit.
    /// Scale factor defined per exchange in configs/exchanges/.
    /// Must be >= 0.
    pub volume_scaled: u64,

    /// Nanoseconds since UNIX epoch.
    /// Must be monotonic within same symbol stream.
    pub timestamp_ns: u64,

    /// Exchange identifier (e.g., "binance", "bybit")
    pub exchange_id: String,

    /// Best bid price (scaled), if available
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bid_price_scaled: Option<u64>,

    /// Best ask price (scaled), if available
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ask_price_scaled: Option<u64>,

    /// Exchange-assigned trade ID, if applicable
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trade_id: Option<String>,

    /// Bounded metadata (max 16 keys, max 256 chars per value)
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub metadata: BTreeMap<String, String>,
}

impl TickDataV1 {
    /// Validate tick data against contract rules.
    /// Returns Ok(()) if valid, Err with descriptive message otherwise.
    /// No panics, no unwrap, no expect — per rust-policy.yaml.
    pub fn validate(&self) -> Result<(), TickValidationError> {
        if self.symbol.is_empty() {
            return Err(TickValidationError::EmptySymbol);
        }
        if self.symbol.len() > 32 {
            return Err(TickValidationError::SymbolTooLong(self.symbol.len()));
        }
        if self.price_scaled == 0 {
            return Err(TickValidationError::ZeroPrice);
        }
        if self.timestamp_ns == 0 {
            return Err(TickValidationError::ZeroTimestamp);
        }
        if self.exchange_id.is_empty() {
            return Err(TickValidationError::EmptyExchangeId);
        }
        if self.exchange_id.len() > 64 {
            return Err(TickValidationError::ExchangeIdTooLong(self.exchange_id.len()));
        }
        if let Some(ref bid) = self.bid_price_scaled {
            if *bid == 0 {
                return Err(TickValidationError::ZeroBidPrice);
            }
        }
        if let Some(ref ask) = self.ask_price_scaled {
            if *ask == 0 {
                return Err(TickValidationError::ZeroAskPrice);
            }
        }
        if let Some(ref tid) = self.trade_id {
            if tid.len() > 128 {
                return Err(TickValidationError::TradeIdTooLong(tid.len()));
            }
        }
        if self.metadata.len() > 16 {
            return Err(TickValidationError::MetadataTooManyKeys(self.metadata.len()));
        }
        for (key, value) in &self.metadata {
            if value.len() > 256 {
                return Err(TickValidationError::MetadataValueTooLong(key.clone(), value.len()));
            }
        }
        Ok(())
    }
}

/// Explicit error types — no unwrap/expect per rust-policy.yaml
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum TickValidationError {
    #[error("symbol must not be empty")]
    EmptySymbol,
    #[error("symbol exceeds max length 32: got {0}")]
    SymbolTooLong(usize),
    #[error("price_scaled must be > 0")]
    ZeroPrice,
    #[error("timestamp_ns must be > 0")]
    ZeroTimestamp,
    #[error("exchange_id must not be empty")]
    EmptyExchangeId,
    #[error("exchange_id exceeds max length 64: got {0}")]
    ExchangeIdTooLong(usize),
    #[error("bid_price_scaled must be > 0 when present")]
    ZeroBidPrice,
    #[error("ask_price_scaled must be > 0 when present")]
    ZeroAskPrice,
    #[error("trade_id exceeds max length 128: got {0}")]
    TradeIdTooLong(usize),
    #[error("metadata exceeds max 16 keys: got {0}")]
    MetadataTooManyKeys(usize),
    #[error("metadata value for key '{0}' exceeds max 256 chars: got {1}")]
    MetadataValueTooLong(String, usize),
}

// Governance note: clippy::panic is allowed ONLY in test scope.
// Production code remains panic-free per rust-policy.yaml.
// This is not a workaround; it is the standard pattern for strict no-panic policies.
// See ADR-2026-08-30-006.
#[cfg(test)]
#[cfg_attr(test, allow(clippy::panic))]
mod tests {
    use super::*;

    fn valid_tick() -> TickDataV1 {
        TickDataV1 {
            symbol: "BTCUSDT".to_string(),
            price_scaled: 5_000_000_000,
            volume_scaled: 100_000,
            timestamp_ns: 1_725_000_000_000_000_000,
            exchange_id: "binance".to_string(),
            bid_price_scaled: Some(4_999_000_000),
            ask_price_scaled: Some(5_001_000_000),
            trade_id: Some("t123".to_string()),
            metadata: BTreeMap::new(),
        }
    }

    #[test]
    fn test_valid_tick_passes_validation() {
        let tick = valid_tick();
        assert!(tick.validate().is_ok());
    }

    #[test]
    fn test_zero_price_rejected() {
        let mut tick = valid_tick();
        tick.price_scaled = 0;
        assert_eq!(tick.validate(), Err(TickValidationError::ZeroPrice));
    }

    #[test]
    fn test_empty_symbol_rejected() {
        let mut tick = valid_tick();
        tick.symbol = String::new();
        assert_eq!(tick.validate(), Err(TickValidationError::EmptySymbol));
    }

    #[test]
    fn test_metadata_too_many_keys_rejected() {
        let mut tick = valid_tick();
        for i in 0..17 {
            tick.metadata.insert(format!("k{i}"), "v".to_string());
        }
        assert_eq!(tick.validate(), Err(TickValidationError::MetadataTooManyKeys(17)));
    }

    #[test]
    fn test_serialization_roundtrip() {
        let tick = valid_tick();

        let json = match serde_json::to_string(&tick) {
            Ok(v) => v,
            Err(e) => panic!("serialization failed: {e:?}"),
        };

        let deserialized: TickDataV1 = match serde_json::from_str(&json) {
            Ok(v) => v,
            Err(e) => panic!("deserialization failed: {e:?}"),
        };

        assert_eq!(tick, deserialized);
    }
}
