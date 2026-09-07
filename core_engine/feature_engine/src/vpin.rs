// MODULE: atlas-feature-engine
// GOVERNANCE: Matrix A - Rust Compute Layer
// FORMULA: VPIN = |buy_vol - sell_vol| / total_vol
use crate::models::TradeRecord;

/// Computes simplified Volume-Synchronized Probability of Informed Trading.
/// Returns value in [0.0, 1.0]. Higher = more toxic flow.
pub fn compute_vpin(trades: &[TradeRecord]) -> f64 {
    let mut buy_vol: f64 = 0.0;
    let mut sell_vol: f64 = 0.0;

    for trade in trades {
        match trade.side.as_str() {
            "buy" => buy_vol += trade.quantity,
            "sell" => sell_vol += trade.quantity,
            _ => {} // Ignore unknown sides
        }
    }

    let total = buy_vol + sell_vol;
    if total == 0.0 {
        return 0.0;
    }

    let vpin = (buy_vol - sell_vol).abs() / total;
    vpin.clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn trade(qty: f64, side: &str) -> TradeRecord {
        TradeRecord { price_scaled: 100, quantity: qty, side: side.to_string() }
    }

    #[test]
    fn test_all_buys() {
        let trades = vec![trade(10.0, "buy"), trade(5.0, "buy")];
        assert!((compute_vpin(&trades) - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_all_sells() {
        let trades = vec![trade(10.0, "sell"), trade(5.0, "sell")];
        assert!((compute_vpin(&trades) - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_balanced() {
        let trades = vec![trade(10.0, "buy"), trade(10.0, "sell")];
        assert!(compute_vpin(&trades).abs() < 1e-9);
    }

    #[test]
    fn test_empty_trades() {
        assert_eq!(compute_vpin(&[]), 0.0);
    }

    #[test]
    fn test_partial_imbalance() {
        let trades = vec![trade(7.0, "buy"), trade(3.0, "sell")];
        let vpin = compute_vpin(&trades);
        assert!((vpin - 0.4).abs() < 1e-9);
    }
}
