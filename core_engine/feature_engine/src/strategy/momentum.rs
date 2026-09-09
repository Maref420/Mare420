// MODULE: atlas-feature-engine::strategy::momentum
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Rate-of-change momentum strategy.
// Measures price acceleration to detect trend continuation.
use std::collections::HashMap;
use super::{Direction, Strategy, StrategySignal};
use crate::models::MarketSnapshot;
use crate::EngineError;

pub struct MomentumStrategy {
    roc_threshold_pct: f64,
}

impl MomentumStrategy {
    pub fn new() -> Self {
        Self { roc_threshold_pct: 0.3 } // 0.3% rate of change threshold
    }
}

impl Default for MomentumStrategy {
    fn default() -> Self { Self::new() }
}

impl Strategy for MomentumStrategy {
    fn id(&self) -> &str { "momentum" }

    fn description(&self) -> &str {
        "Rate-of-change momentum: follow the trend"
    }

    fn compute(&self, snapshot: &MarketSnapshot) -> Result<StrategySignal, EngineError> {
        if snapshot.trades.len() < 2 {
            return Err(EngineError::InvalidData(
                "need at least 2 trades for momentum".into(),
            ));
        }

        let first_price = snapshot.trades.first()
            .ok_or_else(|| EngineError::InvalidData("no first trade".into()))?
            .price_scaled as f64;
        let last_price = snapshot.trades.last()
            .ok_or_else(|| EngineError::InvalidData("no last trade".into()))?
            .price_scaled as f64;

        if first_price <= 0.0 {
            return Err(EngineError::InvalidData("first price must be positive".into()));
        }

        let roc_pct = ((last_price - first_price) / first_price) * 100.0;

        let direction = if roc_pct > self.roc_threshold_pct {
            Direction::Buy
        } else if roc_pct < -self.roc_threshold_pct {
            Direction::Sell
        } else {
            Direction::Neutral
        };

        // Confidence scales with |roc|, capped at 1.0
        let confidence = (roc_pct.abs() / 2.0).min(1.0);

        // Volume-weighted momentum: check if volume supports direction
        let buy_vol: f64 = snapshot.trades.iter()
            .filter(|t| t.side.to_lowercase() == "buy")
            .map(|t| t.quantity)
            .sum();
        let sell_vol: f64 = snapshot.trades.iter()
            .filter(|t| t.side.to_lowercase() == "sell")
            .map(|t| t.quantity)
            .sum();
        let total_vol = buy_vol + sell_vol;
        let vol_ratio = if total_vol > 0.0 {
            (buy_vol - sell_vol) / total_vol
        } else {
            0.0
        };

        // Boost confidence if volume confirms direction
        let vol_confirms = (roc_pct > 0.0 && vol_ratio > 0.0)
            || (roc_pct < 0.0 && vol_ratio < 0.0);
        let final_confidence = if vol_confirms {
            (confidence + 0.15).min(1.0)
        } else {
            confidence
        };

        let mut attrs = HashMap::new();
        attrs.insert("roc_pct".into(), format!("{:.4}", roc_pct));
        attrs.insert("first_price".into(), format!("{:.0}", first_price));
        attrs.insert("last_price".into(), format!("{:.0}", last_price));
        attrs.insert("volume_ratio".into(), format!("{:.4}", vol_ratio));

        Ok(StrategySignal {
            strategy_id: "momentum".into(),
            symbol: snapshot.symbol.clone(),
            direction,
            confidence: final_confidence,
            attributes: attrs,
            timestamp_ns: snapshot.timestamp_ns,
        })
    }
}
