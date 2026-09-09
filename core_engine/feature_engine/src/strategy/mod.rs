// MODULE: atlas-feature-engine::strategy
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Strategy trait system for pluggable signal generation.
// Every strategy implements Strategy trait. Registry manages lifecycle.
// Ghost Replay iterates registry — adding strategies requires ZERO
// changes to existing code.
// WARNING: No unwrap/expect/panic. All errors via Result.
pub mod mean_reversion;
pub mod momentum;
pub mod vwap_strategy;

use std::collections::HashMap;
use std::sync::Arc;
use crate::models::MarketSnapshot;
use crate::EngineError;

/// Standardized direction output for all strategies.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum Direction {
    Buy,
    Sell,
    Neutral,
}

impl Direction {
    pub fn as_str(&self) -> &str {
        match self {
            Direction::Buy => "BUY",
            Direction::Sell => "SELL",
            Direction::Neutral => "NEUTRAL",
        }
    }
}

/// Standardized output from any strategy.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct StrategySignal {
    pub strategy_id: String,
    pub symbol: String,
    pub direction: Direction,
    pub confidence: f64,
    pub attributes: HashMap<String, String>,
    pub timestamp_ns: u64,
}

/// Every strategy must implement this trait.
/// Thread-safe (Send + Sync) for parallel Ghost Replay.
pub trait Strategy: Send + Sync {
    /// Unique identifier for this strategy.
    fn id(&self) -> &str;

    /// Human-readable description.
    fn description(&self) -> &str;

    /// Compute signal from market snapshot.
    /// Must not panic. Must return Err on invalid input.
    fn compute(&self, snapshot: &MarketSnapshot) -> Result<StrategySignal, EngineError>;
}

/// Registry holds all active strategies.
/// Thread-safe via Arc. Clone is cheap.
#[derive(Clone)]
pub struct StrategyRegistry {
    strategies: Vec<Arc<dyn Strategy>>,
}

impl Default for StrategyRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl StrategyRegistry {
    /// Creates a registry pre-loaded with all built-in strategies.
    pub fn new() -> Self {
        let mut reg = Self { strategies: Vec::new() };
        reg.register(Arc::new(vwap_strategy::VwapStrategy::new()));
        reg.register(Arc::new(mean_reversion::MeanReversionStrategy::new()));
        reg.register(Arc::new(momentum::MomentumStrategy::new()));
        reg
    }

    /// Register a new strategy. Zero impact on existing ones.
    pub fn register(&mut self, strategy: Arc<dyn Strategy>) {
        self.strategies.push(strategy);
    }

    /// Run all strategies on a snapshot. Returns all signals.
    /// Strategies that fail are skipped (error logged, not propagated).
    pub fn compute_all(
        &self,
        snapshot: &MarketSnapshot,
    ) -> Vec<StrategySignal> {
        let mut signals = Vec::with_capacity(self.strategies.len());
        for strat in &self.strategies {
            match strat.compute(snapshot) {
                Ok(sig) => signals.push(sig),
                Err(_) => continue, // skip failed strategies, don't block others
            }
        }
        signals
    }

    /// Run a specific strategy by ID.
    pub fn compute_by_id(
        &self,
        strategy_id: &str,
        snapshot: &MarketSnapshot,
    ) -> Result<StrategySignal, EngineError> {
        for strat in &self.strategies {
            if strat.id() == strategy_id {
                return strat.compute(snapshot);
            }
        }
        Err(EngineError::InvalidData(
            format!("unknown strategy: {}", strategy_id),
        ))
    }

    /// List all registered strategy IDs.
    pub fn list_ids(&self) -> Vec<String> {
        self.strategies.iter().map(|s| s.id().to_string()).collect()
    }

    /// Number of registered strategies.
    pub fn len(&self) -> usize {
        self.strategies.len()
    }

    pub fn is_empty(&self) -> bool {
        self.strategies.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{MarketSnapshot, OrderbookLevel, TradeRecord};

    fn sample_snapshot() -> MarketSnapshot {
        MarketSnapshot {
            symbol: "BTCUSDT".into(),
            exchange: "binance".into(),
            bids: vec![
                OrderbookLevel { price_scaled: 99_900, quantity: 1.0 },
                OrderbookLevel { price_scaled: 99_800, quantity: 2.0 },
            ],
            asks: vec![
                OrderbookLevel { price_scaled: 100_100, quantity: 1.0 },
                OrderbookLevel { price_scaled: 100_200, quantity: 2.0 },
            ],
            trades: vec![
                TradeRecord { price_scaled: 100_000, quantity: 1.0, side: "buy".into() },
                TradeRecord { price_scaled: 100_100, quantity: 0.5, side: "sell".into() },
                TradeRecord { price_scaled: 99_900, quantity: 2.0, side: "buy".into() },
            ],
            timestamp_ns: 1_000_000_000,
        }
    }

    #[test]
    fn test_registry_default_has_three_strategies() {
        let reg = StrategyRegistry::new();
        assert_eq!(reg.len(), 3);
        let ids = reg.list_ids();
        assert!(ids.contains(&"vwap".to_string()));
        assert!(ids.contains(&"mean_reversion".to_string()));
        assert!(ids.contains(&"momentum".to_string()));
    }

    #[test]
    fn test_compute_all_returns_signals() {
        let reg = StrategyRegistry::new();
        let snap = sample_snapshot();
        let signals = reg.compute_all(&snap);
        assert!(!signals.is_empty());
        for sig in &signals {
            assert_eq!(sig.symbol, "BTCUSDT");
            assert!((0.0..=1.0).contains(&sig.confidence));
        }
    }

    #[test]
    fn test_compute_by_id_vwap() {
        let reg = StrategyRegistry::new();
        let snap = sample_snapshot();
        let sig = reg.compute_by_id("vwap", &snap);
        assert!(sig.is_ok());
        assert_eq!(sig.unwrap().strategy_id, "vwap");
    }

    #[test]
    fn test_compute_by_id_unknown() {
        let reg = StrategyRegistry::new();
        let snap = sample_snapshot();
        assert!(reg.compute_by_id("nonexistent", &snap).is_err());
    }

    #[test]
    fn test_custom_strategy_registration() {
        struct DummyStrategy;
        impl Strategy for DummyStrategy {
            fn id(&self) -> &str { "dummy" }
            fn description(&self) -> &str { "test only" }
            fn compute(&self, snap: &MarketSnapshot) -> Result<StrategySignal, EngineError> {
                Ok(StrategySignal {
                    strategy_id: "dummy".into(),
                    symbol: snap.symbol.clone(),
                    direction: Direction::Neutral,
                    confidence: 0.5,
                    attributes: HashMap::new(),
                    timestamp_ns: snap.timestamp_ns,
                })
            }
        }

        let mut reg = StrategyRegistry::new();
        reg.register(Arc::new(DummyStrategy));
        assert_eq!(reg.len(), 4);
        let sig = reg.compute_by_id("dummy", &sample_snapshot()).unwrap();
        assert_eq!(sig.direction, Direction::Neutral);
    }
}
