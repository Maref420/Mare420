// MODULE: atlas-feature-engine::strategy::mean_reversion
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Z-score based mean reversion strategy.
// When price deviates significantly from rolling mean, expect reversion.
use std::collections::HashMap;
use super::{Direction, Strategy, StrategySignal};
use crate::models::MarketSnapshot;
use crate::EngineError;

pub struct MeanReversionStrategy {
    z_buy_threshold: f64,
    z_sell_threshold: f64,
}

impl MeanReversionStrategy {
    pub fn new() -> Self {
        Self {
            z_buy_threshold: -1.5,   // buy when z < -1.5
            z_sell_threshold: 1.5,   // sell when z > 1.5
        }
    }
}

impl Default for MeanReversionStrategy {
    fn default() -> Self { Self::new() }
}

impl Strategy for MeanReversionStrategy {
    fn id(&self) -> &str { "mean_reversion" }

    fn description(&self) -> &str {
        "Z-score mean reversion: buy oversold, sell overbought"
    }

    fn compute(&self, snapshot: &MarketSnapshot) -> Result<StrategySignal, EngineError> {
        if snapshot.trades.len() < 3 {
            return Err(EngineError::InvalidData(
                "need at least 3 trades for mean reversion".into(),
            ));
        }

        let prices: Vec<f64> = snapshot.trades.iter()
            .map(|t| t.price_scaled as f64)
            .collect();

        let n = prices.len() as f64;
        let mean: f64 = prices.iter().sum::<f64>() / n;

        let variance: f64 = prices.iter()
            .map(|p| (p - mean).powi(2))
            .sum::<f64>() / n;

        let std_dev = variance.sqrt();
        if std_dev == 0.0 {
            return Err(EngineError::InvalidData("zero variance".into()));
        }

        let current = prices.last()
            .ok_or_else(|| EngineError::InvalidData("no current price".into()))?;
        let z_score = (current - mean) / std_dev;

        let direction = if z_score < self.z_buy_threshold {
            Direction::Buy
        } else if z_score > self.z_sell_threshold {
            Direction::Sell
        } else {
            Direction::Neutral
        };

        // Confidence scales with |z_score|, capped at 1.0
        let confidence = (z_score.abs() / 3.0).min(1.0);

        let mut attrs = HashMap::new();
        attrs.insert("z_score".into(), format!("{:.4}", z_score));
        attrs.insert("mean_price".into(), format!("{:.2}", mean));
        attrs.insert("std_dev".into(), format!("{:.4}", std_dev));
        attrs.insert("sample_count".into(), prices.len().to_string());

        Ok(StrategySignal {
            strategy_id: "mean_reversion".into(),
            symbol: snapshot.symbol.clone(),
            direction,
            confidence,
            attributes: attrs,
            timestamp_ns: snapshot.timestamp_ns,
        })
    }
}
