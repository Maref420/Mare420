// MODULE: atlas-feature-engine
// GOVERNANCE: Matrix A - Rust Compute Layer
// FORMULA: OBI = (bid_qty - ask_qty) / (bid_qty + ask_qty)
use crate::models::OrderbookLevel;

/// Computes Orderbook Imbalance using top `depth` levels.
/// Returns value in [-1.0, 1.0]. Positive = bid-heavy.
pub fn compute_obi(bids: &[OrderbookLevel], asks: &[OrderbookLevel], depth: usize) -> f64 {
    let bid_qty: f64 = bids.iter().take(depth).map(|l| l.quantity).sum();
    let ask_qty: f64 = asks.iter().take(depth).map(|l| l.quantity).sum();
    let total = bid_qty + ask_qty;
    if total == 0.0 {
        return 0.0;
    }
    let obi = (bid_qty - ask_qty) / total;
    obi.clamp(-1.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn level(price: i64, qty: f64) -> OrderbookLevel {
        OrderbookLevel { price_scaled: price, quantity: qty }
    }

    #[test]
    fn test_balanced_book() {
        let bids = vec![level(100, 5.0)];
        let asks = vec![level(101, 5.0)];
        assert!((compute_obi(&bids, &asks, 5) - 0.0).abs() < 1e-9);
    }

    #[test]
    fn test_bid_heavy() {
        let bids = vec![level(100, 8.0)];
        let asks = vec![level(101, 2.0)];
        let obi = compute_obi(&bids, &asks, 5);
        assert!(obi > 0.5);
    }

    #[test]
    fn test_ask_heavy() {
        let bids = vec![level(100, 2.0)];
        let asks = vec![level(101, 8.0)];
        let obi = compute_obi(&bids, &asks, 5);
        assert!(obi < -0.5);
    }

    #[test]
    fn test_empty_book() {
        assert_eq!(compute_obi(&[], &[], 5), 0.0);
    }

    #[test]
    fn test_depth_limit() {
        let bids = vec![level(100, 10.0), level(99, 100.0)];
        let asks = vec![level(101, 10.0)];
        let obi_shallow = compute_obi(&bids, &asks, 1);
        let obi_deep = compute_obi(&bids, &asks, 5);
        assert!(obi_shallow != obi_deep);
    }
}
