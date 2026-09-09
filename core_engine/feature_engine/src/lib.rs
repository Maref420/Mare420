// MODULE: atlas-feature-engine
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: process_snapshot → ForensicsSignal matches Python ResearchAgent input.
// WARNING: No unwrap/expect/panic on request path. All errors via Result.
pub mod aqs;
pub mod latency;
pub mod models;
pub mod obi;
pub mod spoofing;
pub mod vpin;
pub mod vwap;
pub mod strategy;

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

#[cfg(test)]
mod request_path_tests {
    use super::*;
    use crate::models::{MarketSnapshot, OrderbookLevel, TradeRecord};

    /// Helper: creates a valid snapshot for mutation testing.
    fn valid_snapshot() -> MarketSnapshot {
        MarketSnapshot {
            symbol: "BTCUSDT".into(),
            exchange: "bybit".into(),
            bids: vec![OrderbookLevel { price_scaled: 65000, quantity: 1.5 }],
            asks: vec![OrderbookLevel { price_scaled: 65010, quantity: 1.2 }],
            trades: vec![TradeRecord { price_scaled: 65000, quantity: 0.5, side: "buy".into() }],
            timestamp_ns: 1725148800000000000,
        }
    }

    #[test]
    fn request_path_empty_symbol_returns_err_no_panic() {
        let mut snap = valid_snapshot();
        snap.symbol = "".into();
        let result = process_snapshot(&snap, "trace-req-1");
        assert!(result.is_err());
        let err_msg = format!("{}", result.unwrap_err());
        assert!(err_msg.contains("symbol"));
    }

    #[test]
    fn request_path_zero_timestamp_returns_err_no_panic() {
        let mut snap = valid_snapshot();
        snap.timestamp_ns = 0;
        let result = process_snapshot(&snap, "trace-req-2");
        assert!(result.is_err());
    }

    #[test]
    fn request_path_empty_bids_returns_err_no_panic() {
        let mut snap = valid_snapshot();
        snap.bids.clear();
        let result = process_snapshot(&snap, "trace-req-3");
        assert!(result.is_err());
    }

    #[test]
    fn request_path_empty_asks_returns_err_no_panic() {
        let mut snap = valid_snapshot();
        snap.asks.clear();
        let result = process_snapshot(&snap, "trace-req-4");
        assert!(result.is_err());
    }

    #[test]
    fn request_path_negative_price_returns_err_no_panic() {
        let mut snap = valid_snapshot();
        snap.bids[0].price_scaled = -100;
        let result = process_snapshot(&snap, "trace-req-5");
        assert!(result.is_err());
    }

    #[test]
    fn request_path_zero_price_returns_err_no_panic() {
        let mut snap = valid_snapshot();
        snap.bids[0].price_scaled = 0;
        let result = process_snapshot(&snap, "trace-req-6");
        assert!(result.is_err());
    }

    #[test]
    fn request_path_empty_trades_succeeds() {
        let mut snap = valid_snapshot();
        snap.trades.clear();
        // VPIN should return 0.0, not panic
        let result = process_snapshot(&snap, "trace-req-7");
        assert!(result.is_ok());
        let signal = result.unwrap();
        assert_eq!(signal.vpin_toxicity, 0.0);
    }

    #[test]
    fn request_path_extreme_quantities_no_panic() {
        let mut snap = valid_snapshot();
        snap.bids[0].quantity = f64::MAX;
        snap.asks[0].quantity = f64::MAX;
        let result = process_snapshot(&snap, "trace-req-8");
        // Should succeed or return Err, never panic
        match result {
            Ok(signal) => {
                assert!(signal.orderbook_imbalance >= -1.0 && signal.orderbook_imbalance <= 1.0);
                assert!(signal.aqs_score >= 0 && signal.aqs_score <= 100);
                assert!(signal.confidence >= 0.0 && signal.confidence <= 1.0);
            }
            Err(_) => {} // Also acceptable
        }
    }

    #[test]
    fn request_path_huge_spread_clamped_aqs() {
        let mut snap = valid_snapshot();
        snap.asks[0].price_scaled = 999_999_999;
        let result = process_snapshot(&snap, "trace-req-9");
        assert!(result.is_ok());
        let signal = result.unwrap();
        assert!(signal.aqs_score >= 0 && signal.aqs_score <= 100);
    }

    #[test]
    fn request_path_unknown_trade_side_ignored_no_panic() {
        let mut snap = valid_snapshot();
        snap.trades.push(TradeRecord {
            price_scaled: 65000,
            quantity: 1.0,
            side: "unknown_side".into(),
        });
        let result = process_snapshot(&snap, "trace-req-10");
        assert!(result.is_ok());
    }

    #[test]
    fn request_path_source_uri_always_set() {
        let snap = valid_snapshot();
        let signal = process_snapshot(&snap, "trace-req-11").unwrap();
        assert_eq!(signal.source_uri, "rust-feature-engine://v1");
        assert!(!signal.source_uri.is_empty());
    }

    #[test]
    fn request_path_trace_id_propagated() {
        let snap = valid_snapshot();
        let signal = process_snapshot(&snap, "my-trace-id-xyz").unwrap();
        assert_eq!(signal.trace_id, "my-trace-id-xyz");
    }

    #[test]
    fn request_path_output_serializable_no_panic() {
        let snap = valid_snapshot();
        let signal = process_snapshot(&snap, "trace-serde").unwrap();
        let json = serde_json::to_string(&signal).expect("must serialize");
        assert!(!json.is_empty());
        // Verify Python ResearchAgent can parse it
        let parsed: models::ForensicsSignal = serde_json::from_str(&json).expect("must deserialize");
        assert_eq!(parsed.symbol, "BTCUSDT");
    }

    #[test]
    fn request_path_concurrent_calls_no_data_race() {
        use std::thread;
        let mut handles = vec![];
        for i in 0..20 {
            handles.push(thread::spawn(move || {
                let snap = MarketSnapshot {
                    symbol: format!("SYM_{}", i),
                    exchange: "test".into(),
                    bids: vec![OrderbookLevel { price_scaled: 100 + i as i64, quantity: 1.0 }],
                    asks: vec![OrderbookLevel { price_scaled: 101 + i as i64, quantity: 1.0 }],
                    trades: vec![],
                    timestamp_ns: 1_000_000_000 + i as u64,
                };
                let result = process_snapshot(&snap, &format!("trace-{}", i));
                assert!(result.is_ok());
            }));
        }
        for h in handles {
            h.join().expect("thread must not panic");
        }
    }
}
