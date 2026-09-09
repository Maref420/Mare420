// MODULE: atlas-feature-engine::strategy::vwap
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: VWAP strategy implementing Strategy trait.
use std::collections::HashMap;
use super::{Direction, Strategy, StrategySignal};
use crate::models::MarketSnapshot;
use crate::vwap;
use crate::EngineError;

pub struct VwapStrategy {
    deviation_threshold_bps: i32,
}

impl VwapStrategy {
    pub fn new() -> Self {
        Self { deviation_threshold_bps: 50 }
    }

    pub fn with_threshold(threshold_bps: i32) -> Self {
        Self { deviation_threshold_bps: threshold_bps }
    }
}

impl Default for VwapStrategy {
    fn default() -> Self { Self::new() }
}

impl Strategy for VwapStrategy {
    fn id(&self) -> &str { "vwap" }

    fn description(&self) -> &str {
        "Volume-Weighted Average Price deviation with OBV confirmation"
    }

    fn compute(&self, snapshot: &MarketSnapshot) -> Result<StrategySignal, EngineError> {
        if snapshot.trades.is_empty() {
            return Err(EngineError::InvalidData("no trades for VWAP".into()));
        }

        let current_price = snapshot.trades.last()
            .map(|t| t.price_scaled)
            .unwrap_or(0);
        let vwap_val = vwap::compute_vwap(&snapshot.trades)?;
        let obv_val = vwap::compute_obv(&snapshot.trades)?;
        let dev_bps = vwap::compute_vwap_deviation_bps(current_price, vwap_val)?;
        let threshold = self.deviation_threshold_bps;

        let direction = if dev_bps < -threshold && obv_val > 0.0 {
            Direction::Buy
        } else if dev_bps > threshold && obv_val < 0.0 {
            Direction::Sell
        } else {
            Direction::Neutral
        };

        let dev_abs = dev_bps.unsigned_abs() as f64;
        let base_conf = (dev_abs / 500.0).min(1.0);
        let obv_boost = if (dev_bps < 0 && obv_val > 0.0) || (dev_bps > 0 && obv_val < 0.0) {
            0.2
        } else {
            0.0
        };
        let confidence = (base_conf + obv_boost).min(1.0);

        let mut attrs = HashMap::new();
        attrs.insert("vwap_scaled".into(), vwap_val.to_string());
        attrs.insert("deviation_bps".into(), dev_bps.to_string());
        attrs.insert("obv".into(), format!("{:.4}", obv_val));
        attrs.insert("trade_count".into(), snapshot.trades.len().to_string());
        attrs.insert("threshold_bps".into(), threshold.to_string());

        Ok(StrategySignal {
            strategy_id: "vwap".into(),
            symbol: snapshot.symbol.clone(),
            direction,
            confidence,
            attributes: attrs,
            timestamp_ns: snapshot.timestamp_ns,
        })
    }
}
