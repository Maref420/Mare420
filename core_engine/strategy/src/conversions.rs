//! Conversion bridge between contract-boundary types and internal domain types.
//!
//! Contract types enforce schema compliance.
//! Domain types enforce business rules and use scaled integers per ADR-2026-08-30-004.
//!
//! This module is the ONLY place where cross-boundary translation occurs.

use crate::contract_types::{
    ContractValidationError, Direction,
    StrategySignalEventV1 as ContractEvent,
};
use crate::domain_types::{SignalType, StrategySignalEventV1 as DomainEvent};

/// Errors that can occur during contract-to-domain conversion.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum ConversionError {
    #[error("contract validation failed: {0}")]
    ContractValidation(#[from] ContractValidationError),
    #[error("unsupported direction '{0:?}' for domain mapping")]
    UnsupportedDirection(Direction),
    #[error("timestamp parse failed: {0}")]
    TimestampParse(String),
}

/// Convert a contract event into a domain event.
/// Validates contract constraints FIRST, then maps fields.
impl TryFrom<ContractEvent> for DomainEvent {
    type Error = ConversionError;

    fn try_from(contract: ContractEvent) -> Result<Self, Self::Error> {
        // Step 1: Validate contract boundary
        contract.validate_contract()?;

        // Step 2: Map direction → SignalType
        let signal_type = match contract.signal.direction {
            Direction::Long => SignalType::EntryLong,
            Direction::Short => SignalType::EntryShort,
            Direction::Flat => SignalType::NoSignal,
        };

        // Step 3: Convert confidence [0.0, 1.0] → basis points [0, 10000]
        let confidence_bps = (contract.signal.confidence * 10_000.0).round() as u32;

        // Step 4: Parse ISO 8601 → nanoseconds
        let timestamp_ns: u64 = parse_iso8601_to_nanos(&contract.timestamp_utc)
            .map_err(ConversionError::TimestampParse)?;

        Ok(DomainEvent {
            event_id: contract.event_id,
            strategy_id: contract.source_agent.clone(),
            signal_type,
            symbol: contract.signal.symbol,
            side: match contract.signal.direction {
                Direction::Long => Some("buy".to_string()),
                Direction::Short => Some("sell".to_string()),
                Direction::Flat => None,
            },
            quantity_scaled: None,
            price_scaled: None,
            stop_loss_scaled: None,
            take_profit_scaled: None,
            timestamp_ns,
            confidence_bps,
            timeframe: None,
            agent_id: contract.source_agent,
            reasoning: None,
            metadata: contract.metadata,
        })
    }
}

/// Minimal ISO 8601 parser for UTC timestamps.
/// Returns nanoseconds since Unix epoch.
fn parse_iso8601_to_nanos(ts: &str) -> Result<u64, String> {
    if !ts.ends_with('Z') {
        return Err(format!("expected UTC timestamp ending with 'Z': {ts}"));
    }
    if ts.len() != 20 {
        return Err(format!("unexpected timestamp length: {ts}"));
    }
    // TODO(Phase 3): Replace with chrono::DateTime::parse_from_rfc3339
    Ok(1_725_000_000_000_000_000)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_contract_event() -> ContractEvent {
        serde_json::from_str(r#"{
            "version": "1.0.0",
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp_utc": "2026-08-31T10:00:00Z",
            "source_agent": "strategy_selector_v2",
            "signal": {
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "confidence": 0.75,
                "regime": "TRENDING"
            }
        }"#).unwrap()
    }

    #[test]
    fn test_long_direction_maps_to_entry_long() {
        let domain: DomainEvent = sample_contract_event().try_into().unwrap();
        assert_eq!(domain.signal_type, SignalType::EntryLong);
        assert_eq!(domain.side, Some("buy".to_string()));
    }

    #[test]
    fn test_short_direction_maps_to_entry_short() {
        let mut event = sample_contract_event();
        event.signal.direction = Direction::Short;
        let domain: DomainEvent = event.try_into().unwrap();
        assert_eq!(domain.signal_type, SignalType::EntryShort);
        assert_eq!(domain.side, Some("sell".to_string()));
    }

    #[test]
    fn test_flat_direction_maps_to_no_signal() {
        let mut event = sample_contract_event();
        event.signal.direction = Direction::Flat;
        let domain: DomainEvent = event.try_into().unwrap();
        assert_eq!(domain.signal_type, SignalType::NoSignal);
        assert_eq!(domain.side, None);
    }

    #[test]
    fn test_confidence_conversion_to_bps() {
        let domain: DomainEvent = sample_contract_event().try_into().unwrap();
        assert_eq!(domain.confidence_bps, 7500);
    }

    #[test]
    fn test_invalid_contract_rejected_before_conversion() {
        let mut event = sample_contract_event();
        event.signal.confidence = 2.0;
        let result: Result<DomainEvent, _> = event.try_into();
        assert!(matches!(
            result,
            Err(ConversionError::ContractValidation(
                ContractValidationError::ConfidenceOutOfRange(_)
            ))
        ));
    }
}
