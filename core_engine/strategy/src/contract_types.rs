//! Contract-boundary types for strategy-signal-event-v1.
//! These types are a 1:1 mapping of the JSON Schema and MUST NOT
//! contain business logic, scaled integers, or execution semantics.
//!
//! Schema: contracts/schemas/strategy/strategy-signal-event-v1.schema.json
//! Policy: governance/policies/rust-policy.yaml

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use uuid::Uuid;

/// Top-level event envelope matching strategy-signal-event-v1 schema.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StrategySignalEventV1 {
    /// Must be "1.0.0"
    pub version: String,
    pub event_id: Uuid,
    /// ISO 8601 UTC timestamp
    pub timestamp_utc: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_id: Option<Uuid>,
    pub source_agent: String,
    pub signal: Signal,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub metadata: BTreeMap<String, String>,
}

/// Inner signal payload matching schema's `signal` object.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Signal {
    /// Pattern: ^[A-Z0-9]{2,20}$
    pub symbol: String,
    pub direction: Direction,
    /// Range: [0.0, 1.0]
    pub confidence: f64,
    pub regime: MarketRegime,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub parameters: BTreeMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Direction {
    Long,
    Short,
    Flat,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum MarketRegime {
    Trending,
    Ranging,
    Volatile,
    Calm,
}

/// Validation errors specific to contract boundary constraints.
/// NOTE: Cannot derive Eq because ConfidenceOutOfRange contains f64.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum ContractValidationError {
    #[error("version must be '1.0.0', got '{0}'")]
    InvalidVersion(String),
    #[error("source_agent must not be empty")]
    EmptySourceAgent,
    #[error("symbol '{0}' does not match pattern ^[A-Z0-9]{{2,20}}$")]
    InvalidSymbol(String),
    #[error("confidence {0} out of range [0.0, 1.0]")]
    ConfidenceOutOfRange(f64),
    #[error("timestamp_utc '{0}' is not valid ISO 8601")]
    InvalidTimestamp(String),
}

impl StrategySignalEventV1 {
    /// Validate all contract-boundary constraints.
    /// This is NOT business logic — only schema enforcement.
    pub fn validate_contract(&self) -> Result<(), ContractValidationError> {
        if self.version != "1.0.0" {
            return Err(ContractValidationError::InvalidVersion(self.version.clone()));
        }
        if self.source_agent.is_empty() {
            return Err(ContractValidationError::EmptySourceAgent);
        }
        self.signal.validate_contract()
    }
}

impl Signal {
    pub fn validate_contract(&self) -> Result<(), ContractValidationError> {
        // Symbol pattern: ^[A-Z0-9]{2,20}$
        let valid_symbol = self.symbol.len() >= 2
            && self.symbol.len() <= 20
            && self.symbol.chars().all(|c| c.is_ascii_uppercase() || c.is_ascii_digit());
        if !valid_symbol {
            return Err(ContractValidationError::InvalidSymbol(self.symbol.clone()));
        }
        // Confidence range: [0.0, 1.0]
        if !(0.0..=1.0).contains(&self.confidence) {
            return Err(ContractValidationError::ConfidenceOutOfRange(self.confidence));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE_JSON: &str = r#"{
        "version": "1.0.0",
        "event_id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp_utc": "2026-08-31T10:00:00Z",
        "trace_id": "660e8400-e29b-41d4-a716-446655440001",
        "source_agent": "strategy_selector_v2",
        "signal": {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "confidence": 0.87,
            "regime": "TRENDING"
        }
    }"#;

    #[test]
    fn test_deserialize_sample_payload() {
        let event: StrategySignalEventV1 = serde_json::from_str(SAMPLE_JSON)
            .expect("must deserialize sample from envelope doc");
        assert_eq!(event.version, "1.0.0");
        assert_eq!(event.signal.direction, Direction::Long);
        assert_eq!(event.signal.regime, MarketRegime::Trending);
        assert!((event.signal.confidence - 0.87).abs() < f64::EPSILON);
    }

    #[test]
    fn test_roundtrip_serialization() {
        let original: StrategySignalEventV1 = serde_json::from_str(SAMPLE_JSON).unwrap();
        let json = serde_json::to_string(&original).unwrap();
        let restored: StrategySignalEventV1 = serde_json::from_str(&json).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn test_validate_valid_event() {
        let event: StrategySignalEventV1 = serde_json::from_str(SAMPLE_JSON).unwrap();
        assert!(event.validate_contract().is_ok());
    }

    #[test]
    fn test_validate_invalid_version() {
        let mut event: StrategySignalEventV1 = serde_json::from_str(SAMPLE_JSON).unwrap();
        event.version = "2.0.0".to_string();
        assert!(matches!(
            event.validate_contract(),
            Err(ContractValidationError::InvalidVersion(_))
        ));
    }

    #[test]
    fn test_validate_invalid_symbol() {
        let mut event: StrategySignalEventV1 = serde_json::from_str(SAMPLE_JSON).unwrap();
        event.signal.symbol = "x".to_string();
        assert!(matches!(
            event.validate_contract(),
            Err(ContractValidationError::InvalidSymbol(_))
        ));
    }

    #[test]
    fn test_validate_confidence_out_of_range() {
        let mut event: StrategySignalEventV1 = serde_json::from_str(SAMPLE_JSON).unwrap();
        event.signal.confidence = 1.5;
        assert!(matches!(
            event.validate_contract(),
            Err(ContractValidationError::ConfidenceOutOfRange(_))
        ));
    }

    #[test]
    fn test_deny_unknown_fields() {
        let bad_json = r#"{
            "version": "1.0.0",
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp_utc": "2026-08-31T10:00:00Z",
            "source_agent": "test",
            "signal": {
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "confidence": 0.5,
                "regime": "CALM"
            },
            "unexpected_field": true
        }"#;
        assert!(serde_json::from_str::<StrategySignalEventV1>(bad_json).is_err());
    }
}
