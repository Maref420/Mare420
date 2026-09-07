// MODULE: atlas-feature-engine
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: process_snapshot → ForensicsSignal matches Python ResearchAgent input.
// WARNING: No unwrap/expect/panic on request path. All errors via Result.
pub mod aqs;
pub mod latency;
pub mod models;
pub mod obi;
pub mod vpin;

use thiserror::Error;

use crate::models::{ForensicsSignal, MarketSnapshot};

#[derive(Error, Debug)]
pub enum EngineError {
    #[error("empty orderbook for symbol {0}")]
    EmptyOrderbook(String),
    #[error("invalid data: {0}")]
    InvalidData(String),
    #[error("compute error: {0}")]
    ComputeError(String),
}

/// Computes spread in basis points from best bid/ask.
fn compute_spread_bps(bids: &[models::OrderbookLevel], asks: &[models::OrderbookLevel]) -> Result<i32, EngineError> {
    let best_bid = bids.first().ok_or_else(|| EngineError::EmptyOrderbook("no bids".into()))?;
    let best_ask = asks.first().ok_or_else(|| EngineError::EmptyOrderbook("no asks".into()))?;

    if best_bid.price_scaled <= 0 || best_ask.price_scaled <= 0 {
        return Err(EngineError::InvalidData("prices must be positive".into()));
    }

    let mid = (best_bid.price_scaled + best_ask.price_scaled) as f64 / 2.0;
    if mid == 0.0 {
        return Ok(0);
    }

    let spread = (best_ask.price_scaled - best_bid.price_scaled) as f64;
    let bps = ((spread / mid) * 10_000.0).round() as i32;
    Ok(bps.max(0))
}

/// Processes a market snapshot into a forensics signal.
pub fn process_snapshot(snapshot: &MarketSnapshot, trace_id: &str) -> Result<ForensicsSignal, EngineError> {
    if snapshot.symbol.is_empty() {
        return Err(EngineError::InvalidData("symbol cannot be empty".into()));
    }
    if snapshot.timestamp_ns == 0 {
        return Err(EngineError::InvalidData("timestamp_ns must be > 0".into()));
    }

    let spread_bps = compute_spread_bps(&snapshot.bids, &snapshot.asks)?;
    let obi_val = obi::compute_obi(&snapshot.bids, &snapshot.asks, 5);
    let vpin_val = vpin::compute_vpin(&snapshot.trades);
    let aqs_val = aqs::compute_aqs(obi_val, vpin_val, spread_bps, 0.0);
    let confidence = aqs::compute_confidence(aqs_val, vpin_val);

    Ok(ForensicsSignal {
        symbol: snapshot.symbol.clone(),
        raw_spread_bps: spread_bps,
        aqs_score: aqs_val,
        confidence,
        orderbook_imbalance: obi_val,
        vpin_toxicity: vpin_val,
        spoofing_detected: false, // P14 will implement
        trace_id: trace_id.to_string(),
        timestamp_ns: snapshot.timestamp_ns,
        source_uri: "rust-feature-engine://v1".to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{OrderbookLevel, TradeRecord};

    fn sample_snapshot() -> MarketSnapshot {
        MarketSnapshot {
            symbol: "BTCUSDT".into(),
            exchange: "bybit".into(),
            bids: vec![
                OrderbookLevel { price_scaled: 65000, quantity: 1.5 },
                OrderbookLevel { price_scaled: 64999, quantity: 2.0 },
            ],
            asks: vec![
                OrderbookLevel { price_scaled: 65010, quantity: 1.2 },
                OrderbookLevel { price_scaled: 65015, quantity: 3.0 },
            ],
            trades: vec![
                TradeRecord { price_scaled: 65000, quantity: 0.5, side: "buy".into() },
                TradeRecord { price_scaled: 65010, quantity: 0.3, side: "sell".into() },
            ],
            timestamp_ns: 1725148800000000000,
        }
    }

    #[test]
    fn test_process_snapshot_success() {
        let snap = sample_snapshot();
        let signal = process_snapshot(&snap, "trace-1").unwrap();
        assert_eq!(signal.symbol, "BTCUSDT");
        assert!(signal.aqs_score >= 0 && signal.aqs_score <= 100);
        assert!(signal.confidence >= 0.0 && signal.confidence <= 1.0);
        assert!(signal.orderbook_imbalance >= -1.0 && signal.orderbook_imbalance <= 1.0);
        assert!(signal.vpin_toxicity >= 0.0 && signal.vpin_toxicity <= 1.0);
        assert_eq!(signal.source_uri, "rust-feature-engine://v1");
        assert!(!signal.spoofing_detected);
    }

    #[test]
    fn test_empty_symbol_rejected() {
        let mut snap = sample_snapshot();
        snap.symbol = "".into();
        assert!(process_snapshot(&snap, "t").is_err());
    }

    #[test]
    fn test_zero_timestamp_rejected() {
        let mut snap = sample_snapshot();
        snap.timestamp_ns = 0;
        assert!(process_snapshot(&snap, "t").is_err());
    }

    #[test]
    fn test_empty_orderbook_rejected() {
        let mut snap = sample_snapshot();
        snap.bids.clear();
        assert!(process_snapshot(&snap, "t").is_err());
    }

    #[test]
    fn test_serialization_roundtrip() {
        let snap = sample_snapshot();
        let signal = process_snapshot(&snap, "trace-serde").unwrap();
        let json = serde_json::to_string(&signal).unwrap();
        let parsed: ForensicsSignal = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.symbol, signal.symbol);
        assert_eq!(parsed.aqs_score, signal.aqs_score);
    }
}
