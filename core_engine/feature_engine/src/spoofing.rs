// MODULE: atlas-feature-engine
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Spoofing/Layering detection on orderbook snapshots.
// WARNING: No unwrap/expect/panic on request path. All functions safe.
// §17: Written directly — no external AI for risk systems.
use std::collections::VecDeque;

use crate::models::{MarketSnapshot, OrderbookLevel};

/// Result of spoofing analysis on a sequence of snapshots.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SpoofingResult {
    pub spoofing_detected: bool,
    pub score: f64,
    pub method: String,
    pub details: String,
}

impl Default for SpoofingResult {
    fn default() -> Self {
        Self {
            spoofing_detected: false,
            score: 0.0,
            method: "none".to_string(),
            details: "insufficient data".to_string(),
        }
    }
}

/// Tracks recent orderbook states for temporal analysis.
#[derive(Debug, Clone)]
pub struct SpoofingDetector {
    history: VecDeque<SnapshotSummary>,
    max_history: usize,
    score_threshold: f64,
}

#[derive(Debug, Clone)]
struct SnapshotSummary {
    timestamp_ns: u64,
    bid_depth_qty: Vec<f64>,
    ask_depth_qty: Vec<f64>,
    best_bid: i64,
    best_ask: i64,
}

/// Filters out zero-quantity levels and returns sanitized OrderbookLevel vec.
fn sanitize_levels(levels: &[OrderbookLevel]) -> Vec<OrderbookLevel> {
    levels.iter().filter(|l| l.quantity > 0.0).cloned().collect()
}

impl SpoofingDetector {
    pub fn new(max_history: usize, score_threshold: f64) -> Self {
        Self {
            history: VecDeque::with_capacity(max_history),
            max_history,
            score_threshold: score_threshold.clamp(0.0, 1.0),
        }
    }

    /// Records a snapshot and returns spoofing analysis.
    pub fn analyze(&mut self, snapshot: &MarketSnapshot) -> SpoofingResult {
        let summary = self.summarize(snapshot);
        self.push_summary(summary.clone());

        if self.history.len() < 2 {
            return SpoofingResult::default();
        }

        let layering_score = self.detect_layering(&summary);
        let imbalance_score = self.detect_imbalance_reversal(&summary);
        let stuffing_score = self.detect_quote_stuffing(&summary);
        let jump_score = self.detect_best_price_jumping(&summary);

        let scores = [layering_score, imbalance_score, stuffing_score, jump_score];
        let max_score = scores.iter().copied().fold(0.0_f64, f64::max);

        let method = if layering_score >= imbalance_score
            && layering_score >= stuffing_score
            && layering_score >= jump_score
        {
            "layering"
        } else if imbalance_score >= stuffing_score && imbalance_score >= jump_score {
            "imbalance_reversal"
        } else if jump_score > 0.0 && jump_score >= stuffing_score {
            "price_jumping"
        } else {
            "quote_stuffing"
        };

        let detected = max_score >= self.score_threshold;

        SpoofingResult {
            spoofing_detected: detected,
            score: (max_score * 100.0).round() / 100.0,
            method: method.to_string(),
            details: if detected {
                format!("{} score {:.2} exceeds threshold {:.2}", method, max_score, self.score_threshold)
            } else {
                format!("all scores below threshold {:.2}", self.score_threshold)
            },
        }
    }

    fn summarize(&self, snapshot: &MarketSnapshot) -> SnapshotSummary {
        let bids = sanitize_levels(&snapshot.bids);
        let asks = sanitize_levels(&snapshot.asks);
        let depth = 10;
        let bid_depth_qty: Vec<f64> = bids.iter().take(depth).map(|l| l.quantity).collect();
        let ask_depth_qty: Vec<f64> = asks.iter().take(depth).map(|l| l.quantity).collect();
        let best_bid = bids.first().map_or(0, |l| l.price_scaled);
        let best_ask = asks.first().map_or(0, |l| l.price_scaled);

        SnapshotSummary {
            timestamp_ns: snapshot.timestamp_ns,
            bid_depth_qty,
            ask_depth_qty,
            best_bid,
            best_ask,
        }
    }

    fn push_summary(&mut self, summary: SnapshotSummary) {
        if self.history.len() >= self.max_history {
            self.history.pop_front();
        }
        self.history.push_back(summary);
    }

    /// Layering: large orders at depth 3+ that vanish in the latest snapshot.
    fn detect_layering(&self, current: &SnapshotSummary) -> f64 {
        let len = self.history.len();
        if len < 2 {
            return 0.0;
        }
        let prev = &self.history[len - 2];
        let mut max_vanish: f64 = 0.0;

        for idx in 2..current.bid_depth_qty.len().min(prev.bid_depth_qty.len()) {
            let pq = prev.bid_depth_qty[idx];
            let cq = current.bid_depth_qty[idx];
            if pq > 1.0 {
                let v = (pq - cq).max(0.0) / pq;
                if v > max_vanish {
                    max_vanish = v;
                }
            }
        }
        for idx in 2..current.ask_depth_qty.len().min(prev.ask_depth_qty.len()) {
            let pq = prev.ask_depth_qty[idx];
            let cq = current.ask_depth_qty[idx];
            if pq > 1.0 {
                let v = (pq - cq).max(0.0) / pq;
                if v > max_vanish {
                    max_vanish = v;
                }
            }
        }
        max_vanish.clamp(0.0, 1.0)
    }

    /// Imbalance reversal: compares current OBI against historical mean + window flips.
    fn detect_imbalance_reversal(&self, current: &SnapshotSummary) -> f64 {
        let current_obi = Self::quick_obi(current);
        let mut window_score = 0.0_f64;

        // Window flip detection across history
        if self.history.len() >= 3 {
            let summaries: Vec<&SnapshotSummary> = self.history.iter().collect();
            for w in summaries.windows(2) {
                let obi_a = Self::quick_obi(w[0]);
                let obi_b = Self::quick_obi(w[1]);
                if obi_a.abs() > 0.3 && obi_b.abs() > 0.3 && obi_a.signum() != obi_b.signum() {
                    window_score = 1.0;
                }
            }
        }

        // Current vs historical mean comparison
        let mut history_score = 0.0_f64;
        let total = self.history.len();
        if total >= 3 {
            let mut sum_obi = 0.0_f64;
            let mut count = 0_usize;
            for (i, s) in self.history.iter().enumerate() {
                if i == total - 1 {
                    continue; // skip last (it IS current, already pushed)
                }
                sum_obi += Self::quick_obi(s);
                count += 1;
            }
            if count > 0 {
                let mean_obi = sum_obi / count as f64;
                if current_obi.abs() > 0.3 && mean_obi.abs() > 0.3 && current_obi.signum() != mean_obi.signum() {
                    history_score = 1.0;
                }
            }
        }

        window_score.max(history_score)
    }

    /// Quote stuffing: rapid changes in total depth quantity.
    fn detect_quote_stuffing(&self, current: &SnapshotSummary) -> f64 {
        let len = self.history.len();
        if len < 2 {
            return 0.0;
        }
        let prev = &self.history[len - 2];
        let prev_total: f64 = prev.bid_depth_qty.iter().sum::<f64>() + prev.ask_depth_qty.iter().sum::<f64>();
        let curr_total: f64 = current.bid_depth_qty.iter().sum::<f64>() + current.ask_depth_qty.iter().sum::<f64>();

        if prev_total == 0.0 {
            return 0.0;
        }
        let change_ratio = (curr_total - prev_total).abs() / prev_total;
        let time_delta_ms = if current.timestamp_ns > prev.timestamp_ns {
            (current.timestamp_ns - prev.timestamp_ns) as f64 / 1_000_000.0
        } else {
            return 0.0;
        };
        if time_delta_ms < 0.001 {
            return 0.0;
        }
        let rate = change_ratio / (time_delta_ms / 1000.0);
        (rate / 10.0).clamp(0.0, 1.0)
    }

    /// Best price jumping: rapid top-of-book moves indicate quote manipulation.
    /// Uses best_bid and best_ask fields from SnapshotSummary.
    fn detect_best_price_jumping(&self, current: &SnapshotSummary) -> f64 {
        let len = self.history.len();
        if len < 2 {
            return 0.0;
        }
        let prev = &self.history[len - 2];
        let bid_jump = (current.best_bid - prev.best_bid).abs();
        let ask_jump = (current.best_ask - prev.best_ask).abs();

        const TICK_THRESHOLD: i64 = 1;
        let mut jumps = 0_u32;
        if bid_jump > TICK_THRESHOLD {
            jumps += 1;
        }
        if ask_jump > TICK_THRESHOLD {
            jumps += 1;
        }
        let transitions = (len - 1) as f64;
        if transitions < 1.0 {
            return 0.0;
        }
        (jumps as f64 / transitions).clamp(0.0, 1.0)
    }

    fn quick_obi(summary: &SnapshotSummary) -> f64 {
        let bid: f64 = summary.bid_depth_qty.iter().sum();
        let ask: f64 = summary.ask_depth_qty.iter().sum();
        let total = bid + ask;
        if total == 0.0 {
            return 0.0;
        }
        (bid - ask) / total
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::TradeRecord;

    fn make_snapshot(ts: u64, bids: Vec<(i64, f64)>, asks: Vec<(i64, f64)>) -> MarketSnapshot {
        MarketSnapshot {
            symbol: "BTCUSDT".into(),
            exchange: "bybit".into(),
            bids: bids.into_iter().map(|(p, q)| OrderbookLevel { price_scaled: p, quantity: q }).collect(),
            asks: asks.into_iter().map(|(p, q)| OrderbookLevel { price_scaled: p, quantity: q }).collect(),
            trades: vec![],
            timestamp_ns: ts,
        }
    }

    #[test]
    fn test_no_spoofing_stable_book() {
        let mut det = SpoofingDetector::new(10, 0.7);
        let s1 = make_snapshot(1_000_000_000, vec![(100, 5.0), (99, 3.0), (98, 2.0)], vec![(101, 5.0), (102, 3.0)]);
        let s2 = make_snapshot(1_100_000_000, vec![(100, 5.0), (99, 3.0), (98, 2.0)], vec![(101, 5.0), (102, 3.0)]);
        assert!(!det.analyze(&s1).spoofing_detected);
        assert!(!det.analyze(&s2).spoofing_detected);
    }

    #[test]
    fn test_layering_large_order_vanishes() {
        let mut det = SpoofingDetector::new(10, 0.5);
        let s1 = make_snapshot(1_000_000_000, vec![(100, 1.0), (99, 1.0), (98, 50.0)], vec![(101, 1.0)]);
        let s2 = make_snapshot(1_200_000_000, vec![(100, 1.0), (99, 1.0), (98, 0.5)], vec![(101, 1.0)]);
        det.analyze(&s1);
        let r = det.analyze(&s2);
        assert!(r.score > 0.5, "Expected high layering, got {}", r.score);
        assert_eq!(r.method, "layering");
    }

    #[test]
    fn test_imbalance_reversal() {
        let mut det = SpoofingDetector::new(10, 0.5);
        det.analyze(&make_snapshot(1_000_000_000, vec![(100, 20.0)], vec![(101, 2.0)]));
        det.analyze(&make_snapshot(1_100_000_000, vec![(100, 2.0)], vec![(101, 20.0)]));
        let r = det.analyze(&make_snapshot(1_200_000_000, vec![(100, 20.0)], vec![(101, 2.0)]));
        assert!(r.score > 0.0, "Expected imbalance reversal");
    }

    #[test]
    fn test_insufficient_data_returns_default() {
        let mut det = SpoofingDetector::new(10, 0.7);
        let r = det.analyze(&make_snapshot(1_000_000_000, vec![(100, 5.0)], vec![(101, 5.0)]));
        assert!(!r.spoofing_detected);
        assert_eq!(r.method, "none");
    }

    #[test]
    fn test_score_clamped() {
        let mut det = SpoofingDetector::new(10, 0.7);
        det.analyze(&make_snapshot(1_000_000_000, vec![(100, 5.0)], vec![(101, 5.0)]));
        let r = det.analyze(&make_snapshot(2_000_000_000, vec![(100, 5.0)], vec![(101, 5.0)]));
        assert!(r.score >= 0.0 && r.score <= 1.0);
    }

    #[test]
    fn test_serialization_roundtrip() {
        let result = SpoofingResult {
            spoofing_detected: true, score: 0.87,
            method: "layering".into(), details: "test".into(),
        };
        let json = serde_json::to_string(&result).expect("serialize");
        let parsed: SpoofingResult = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(parsed.score, 0.87);
        assert!(parsed.spoofing_detected);
    }

    #[test]
    fn test_layering_with_trades_present() {
        // Validates TradeRecord usage: detector should not false-positive on normal trades
        let mut det = SpoofingDetector::new(10, 0.5);
        let mut s1 = make_snapshot(1_000_000_000, vec![(100, 1.0), (99, 1.0), (98, 50.0)], vec![(101, 1.0)]);
        s1.trades = vec![
            TradeRecord { price_scaled: 100, quantity: 1.0, side: "buy".into() },
            TradeRecord { price_scaled: 101, quantity: 0.5, side: "sell".into() },
        ];
        let s2 = make_snapshot(1_200_000_000, vec![(100, 1.0), (99, 1.0), (98, 0.5)], vec![(101, 1.0)]);
        det.analyze(&s1);
        let r = det.analyze(&s2);
        assert!(r.score > 0.5, "Layering should detect even with trades, got {}", r.score);
    }

    #[test]
    fn test_price_jumping_detected() {
        let mut det = SpoofingDetector::new(10, 0.5);
        // Stable prices first
        det.analyze(&make_snapshot(1_000_000_000, vec![(100, 5.0)], vec![(101, 5.0)]));
        // Big price jump
        let r = det.analyze(&make_snapshot(1_100_000_000, vec![(110, 5.0)], vec![(115, 5.0)]));
        assert!(r.score > 0.0, "Expected price jumping signal, got {}", r.score);
    }

    #[test]
    fn test_sanitize_levels_filters_zeros() {
        let levels = vec![
            OrderbookLevel { price_scaled: 100, quantity: 5.0 },
            OrderbookLevel { price_scaled: 99, quantity: 0.0 },
            OrderbookLevel { price_scaled: 98, quantity: 3.0 },
        ];
        let clean = sanitize_levels(&levels);
        assert_eq!(clean.len(), 2);
        assert_eq!(clean[0].price_scaled, 100);
        assert_eq!(clean[1].price_scaled, 98);
    }
}
