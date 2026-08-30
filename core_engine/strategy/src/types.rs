//! Strategy Signal Types
//! Governed by contracts/schemas/events/strategy-signal-event-v1.json
//! All numeric fields use scaled integers per ADR-2026-08-30-004.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SignalType {
    EntryLong,
    EntryShort,
    ExitLong,
    ExitShort,
    AdjustPosition,
    NoSignal,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StrategySignalEventV1 {
    pub event_id: Uuid,
    pub strategy_id: String,
    pub signal_type: SignalType,
    pub symbol: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub side: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub quantity_scaled: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub price_scaled: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stop_loss_scaled: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub take_profit_scaled: Option<u64>,
    pub timestamp_ns: u64,
    /// Confidence in basis points: 5000 = 50.00%
    pub confidence_bps: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timeframe: Option<String>,
    pub agent_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reasoning: Option<String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub metadata: BTreeMap<String, String>,
}

impl StrategySignalEventV1 {
    pub fn validate(&self) -> Result<(), StrategyValidationError> {
        if self.strategy_id.is_empty() {
            return Err(StrategyValidationError::EmptyStrategyId);
        }
        if self.symbol.is_empty() || self.symbol.len() > 32 {
            return Err(StrategyValidationError::InvalidSymbol);
        }
        if self.confidence_bps > 10_000 {
            return Err(StrategyValidationError::ConfidenceOutOfRange(self.confidence_bps));
        }
        if self.timestamp_ns == 0 {
            return Err(StrategyValidationError::ZeroTimestamp);
        }
        if self.agent_id.is_empty() {
            return Err(StrategyValidationError::EmptyAgentId);
        }
        // side required for entry/exit signals
        let needs_side = matches!(
            self.signal_type,
            SignalType::EntryLong | SignalType::EntryShort | SignalType::ExitLong | SignalType::ExitShort
        );
        if needs_side && self.side.is_none() {
            return Err(StrategyValidationError::SideRequiredForSignal);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum StrategyValidationError {
    #[error("strategy_id must not be empty")]
    EmptyStrategyId,
    #[error("symbol must be 1-32 chars")]
    InvalidSymbol,
    #[error("confidence_bps out of range 0-10000: got {0}")]
    ConfidenceOutOfRange(u32),
    #[error("timestamp_ns must be > 0")]
    ZeroTimestamp,
    #[error("agent_id must not be empty")]
    EmptyAgentId,
    #[error("side required for entry/exit signals")]
    SideRequiredForSignal,
}

#[cfg(test)]
#[cfg_attr(test, allow(clippy::panic))]
mod tests {
    use super::*;

    fn valid_signal() -> StrategySignalEventV1 {
        StrategySignalEventV1 {
            event_id: Uuid::new_v4(),
            strategy_id: "momentum-v2".to_string(),
            signal_type: SignalType::EntryLong,
            symbol: "BTCUSDT".to_string(),
            side: Some("buy".to_string()),
            quantity_scaled: Some(100_000),
            price_scaled: Some(5_000_000_000),
            stop_loss_scaled: Some(4_800_000_000),
            take_profit_scaled: Some(5_500_000_000),
            timestamp_ns: 1_725_000_000_000_000_000,
            confidence_bps: 7500,
            timeframe: Some("1h".to_string()),
            agent_id: "strategy-agent-01".to_string(),
            reasoning: Some("RSI oversold + volume spike".to_string()),
            metadata: BTreeMap::new(),
        }
    }

    #[test]
    fn test_valid_signal_passes() {
        assert!(valid_signal().validate().is_ok());
    }

    #[test]
    fn test_entry_without_side_fails() {
        let mut s = valid_signal();
        s.side = None;
        assert_eq!(s.validate(), Err(StrategyValidationError::SideRequiredForSignal));
    }

    #[test]
    fn test_no_signal_without_side_passes() {
        let mut s = valid_signal();
        s.signal_type = SignalType::NoSignal;
        s.side = None;
        assert!(s.validate().is_ok());
    }

    #[test]
    fn test_confidence_out_of_range() {
        let mut s = valid_signal();
        s.confidence_bps = 10_001;
        assert_eq!(s.validate(), Err(StrategyValidationError::ConfidenceOutOfRange(10_001)));
    }

    #[test]
    fn test_serialization_roundtrip() {
        let s = valid_signal();
        let json = match serde_json::to_string(&s) {
            Ok(v) => v,
            Err(e) => panic!("serialization failed: {e:?}"),
        };
        let d: StrategySignalEventV1 = match serde_json::from_str(&json) {
            Ok(v) => v,
            Err(e) => panic!("deserialization failed: {e:?}"),
        };
        assert_eq!(s, d);
    }
}
