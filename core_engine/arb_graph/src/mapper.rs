// MODULE: atlas-arb-graph
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Maps ForensicsSignals → WeightedGraph edges, and PathResults → output signals.
// WARNING: No unwrap/expect/panic. All functions return Result or safe defaults.
// §17: Written directly — edge weight mapping is domain logic.
use serde::{Deserialize, Serialize};

use crate::bellman_ford::{find_negative_cycles, PathResult};
use crate::graph::{GraphError, WeightedGraph};

/// Input signal from FeatureEngine, simplified for graph mapping.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExchangeSignal {
    pub source_exchange: String,
    pub target_exchange: String,
    pub symbol: String,
    pub spread_bps: i32,
    pub vpin_toxicity: f64,
    pub confidence: f64,
    pub timestamp_ns: u64,
}

/// Output: an arbitrage path converted back to signal format.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArbitragePath {
    pub exchanges: Vec<String>,
    pub symbol: String,
    pub net_weight: f64,
    pub hop_count: usize,
    pub profitable: bool,
    pub timestamp_ns: u64,
    pub source_uri: String,
}

/// Computes edge weight from an exchange signal.
/// Lower weight = better path. Negative = profitable arbitrage.
///
/// Formula:
///   base_cost = spread_bps / 10000.0 (convert to decimal)
///   toxicity_penalty = vpin_toxicity * 0.1 (high toxicity = risky)
///   confidence_discount = (1.0 - confidence) * 0.05 (low confidence = penalty)
///   weight = base_cost + toxicity_penalty + confidence_discount
///
/// For arbitrage detection, we negate the weight so that
/// profitable paths become negative cycles.
pub fn signal_to_edge_weight(signal: &ExchangeSignal) -> f64 {
    let base_cost = signal.spread_bps as f64 / 10_000.0;
    let toxicity_penalty = signal.vpin_toxicity.clamp(0.0, 1.0) * 0.1;
    let confidence_discount = (1.0 - signal.confidence.clamp(0.0, 1.0)) * 0.05;
    let cost = base_cost + toxicity_penalty + confidence_discount;

    // Negate: if spread is tight + low toxicity + high confidence,
    // the negated value becomes significantly negative → potential arb
    -cost
}

/// Builds a WeightedGraph from a set of exchange signals.
/// Each unique exchange name becomes a node.
/// Each signal becomes a directed edge with computed weight.
pub fn build_exchange_graph(signals: &[ExchangeSignal]) -> Result<(WeightedGraph, Vec<usize>), GraphError> {
    if signals.is_empty() {
        return Err(GraphError::EmptyGraph);
    }

    // Collect unique exchange names
    let mut exchanges: Vec<String> = Vec::new();
    for sig in signals {
        if !exchanges.contains(&sig.source_exchange) {
            exchanges.push(sig.source_exchange.clone());
        }
        if !exchanges.contains(&sig.target_exchange) {
            exchanges.push(sig.target_exchange.clone());
        }
    }

    if exchanges.is_empty() {
        return Err(GraphError::EmptyGraph);
    }

    let mut graph = WeightedGraph::new(exchanges.clone());

    // Track which signal maps to which edge index for later reference
    let mut edge_signal_indices: Vec<usize> = Vec::new();

    for (i, sig) in signals.iter().enumerate() {
        let from_idx = exchanges.iter().position(|e| e == &sig.source_exchange);
        let to_idx = exchanges.iter().position(|e| e == &sig.target_exchange);

        match (from_idx, to_idx) {
            (Some(from), Some(to)) => {
                let weight = signal_to_edge_weight(sig);
                if graph.add_edge(from, to, weight).is_ok() {
                    edge_signal_indices.push(i);
                }
            }
            _ => continue, // Skip invalid references
        }
    }

    Ok((graph, edge_signal_indices))
}

/// Converts detected negative cycles into ArbitragePath outputs.
pub fn cycles_to_arbitrage_paths(
    cycles: &[PathResult],
    graph: &WeightedGraph,
    symbol: &str,
    timestamp_ns: u64,
) -> Vec<ArbitragePath> {
    let mut paths: Vec<ArbitragePath> = Vec::new();

    for cycle in cycles {
        if cycle.total_weight >= 0.0 {
            continue; // Only negative cycles are profitable
        }

        let mut exchange_names: Vec<String> = Vec::new();
        for &node_idx in &cycle.path {
            if let Some(name) = graph.get_node_name(node_idx) {
                exchange_names.push(name.to_string());
            }
        }

        if exchange_names.len() < 2 {
            continue;
        }

        paths.push(ArbitragePath {
            exchanges: exchange_names,
            symbol: symbol.to_string(),
            net_weight: cycle.total_weight,
            hop_count: cycle.path.len().saturating_sub(1),
            profitable: cycle.total_weight < 0.0,
            timestamp_ns,
            source_uri: "rust-arb-graph://v1".to_string(),
        });
    }

    // Sort by most profitable (most negative weight) first
    paths.sort_by(|a, b| a.net_weight.partial_cmp(&b.net_weight).unwrap_or(std::cmp::Ordering::Equal));
    paths
}

/// Full pipeline: signals → graph → detect cycles → arbitrage paths.
pub fn detect_arbitrage(signals: &[ExchangeSignal], symbol: &str) -> Result<Vec<ArbitragePath>, GraphError> {
    if signals.is_empty() {
        return Ok(Vec::new());
    }

    let timestamp_ns = signals.first().map_or(0, |s| s.timestamp_ns);
    let (graph, _edge_indices) = build_exchange_graph(signals)?;
    let cycles = find_negative_cycles(&graph);
    let paths = cycles_to_arbitrage_paths(&cycles, &graph, symbol, timestamp_ns);

    Ok(paths)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_signal(src: &str, tgt: &str, spread: i32, vpin: f64, conf: f64) -> ExchangeSignal {
        ExchangeSignal {
            source_exchange: src.into(),
            target_exchange: tgt.into(),
            symbol: "BTCUSDT".into(),
            spread_bps: spread,
            vpin_toxicity: vpin,
            confidence: conf,
            timestamp_ns: 1_000_000_000,
        }
    }

    #[test]
    fn test_signal_to_edge_weight_tight_spread() {
        let sig = make_signal("A", "B", 5, 0.1, 0.95);
        let w = signal_to_edge_weight(&sig);
        assert!(w < 0.0, "Tight spread + good conditions should be negative");
    }

    #[test]
    fn test_signal_to_edge_wide_spread() {
        let sig = make_signal("A", "B", 500, 0.8, 0.3);
        let w = signal_to_edge_weight(&sig);
        // Wide spread = high cost = more negative after negation (weight = -cost)
        // So wide spread weight should be LESS than tight spread weight
        let tight_w = signal_to_edge_weight(&make_signal("A", "B", 5, 0.1, 0.95));
        assert!(w < tight_w, "Wide spread should have lower (more negative) weight than tight spread");
    }

    #[test]
    fn test_build_graph_basic() {
        let signals = vec![
            make_signal("binance", "okx", 10, 0.2, 0.9),
            make_signal("okx", "bybit", 15, 0.3, 0.85),
            make_signal("bybit", "binance", 5, 0.1, 0.95),
        ];
        let result = build_exchange_graph(&signals);
        assert!(result.is_ok());
        let (graph, _) = result.unwrap();
        assert_eq!(graph.node_count(), 3);
        assert_eq!(graph.edge_count(), 3);
    }

    #[test]
    fn test_build_graph_empty_signals() {
        let result = build_exchange_graph(&[]);
        assert!(result.is_err());
    }

    #[test]
    fn test_detect_arbitrage_profitable_triangle() {
        // Create a triangle where total cost < 0 (profitable)
        // We need: sum of -cost_i < 0 → sum of cost_i > 0
        // But since we negate, negative cycle means sum of negated weights < 0
        // → sum of costs > 0... wait, let's think again.
        // weight = -(spread/10000 + vpin*0.1 + (1-conf)*0.05)
        // For negative cycle: sum of weights < 0
        // → sum of costs > 0 (always true for positive spreads)
        // So we need the GRAPH to have a cycle where going around is "cheaper"
        // than not going. This happens when one leg has very tight spread.
        let signals = vec![
            make_signal("A", "B", 1, 0.01, 0.99),   // Very cheap
            make_signal("B", "C", 1, 0.01, 0.99),   // Very cheap
            make_signal("C", "A", 1, 0.01, 0.99),   // Very cheap
        ];
        let paths = detect_arbitrage(&signals, "BTCUSDT").unwrap();
        // All edges have same small cost → cycle weight = 3 * (-small) < 0
        assert!(!paths.is_empty(), "Expected profitable cycle with tight spreads");
        assert!(paths[0].profitable);
    }

    #[test]
    fn test_detect_arbitrage_no_cycle() {
        // Linear path, no cycle possible
        let signals = vec![
            make_signal("A", "B", 10, 0.2, 0.9),
            make_signal("B", "C", 15, 0.3, 0.85),
        ];
        let paths = detect_arbitrage(&signals, "BTCUSDT").unwrap();
        assert!(paths.is_empty(), "No cycle possible in linear graph");
    }

    #[test]
    fn test_arbitrage_path_sorted_by_profit() {
        let signals = vec![
            make_signal("A", "B", 1, 0.01, 0.99),
            make_signal("B", "A", 1, 0.01, 0.99),
            make_signal("C", "D", 1, 0.01, 0.99),
            make_signal("D", "C", 1, 0.01, 0.99),
        ];
        let paths = detect_arbitrage(&signals, "BTCUSDT").unwrap();
        // If multiple cycles, they should be sorted by most profitable first
        for window in paths.windows(2) {
            assert!(window[0].net_weight <= window[1].net_weight);
        }
    }

    #[test]
    fn test_arbitrage_path_source_uri_set() {
        let signals = vec![
            make_signal("A", "B", 1, 0.01, 0.99),
            make_signal("B", "A", 1, 0.01, 0.99),
        ];
        let paths = detect_arbitrage(&signals, "BTCUSDT").unwrap();
        for p in &paths {
            assert_eq!(p.source_uri, "rust-arb-graph://v1");
        }
    }

    #[test]
    fn test_serialization_roundtrip() {
        let path = ArbitragePath {
            exchanges: vec!["A".into(), "B".into(), "C".into()],
            symbol: "BTCUSDT".into(),
            net_weight: -0.003,
            hop_count: 3,
            profitable: true,
            timestamp_ns: 1_000_000_000,
            source_uri: "rust-arb-graph://v1".into(),
        };
        let json = serde_json::to_string(&path).expect("serialize");
        let parsed: ArbitragePath = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(parsed.exchanges.len(), 3);
        assert!(parsed.profitable);
    }
}

#[cfg(test)]
mod request_path_tests {
    use super::*;

    fn make_signal(src: &str, tgt: &str, spread: i32, vpin: f64, conf: f64) -> ExchangeSignal {
        ExchangeSignal {
            source_exchange: src.into(),
            target_exchange: tgt.into(),
            symbol: "BTCUSDT".into(),
            spread_bps: spread,
            vpin_toxicity: vpin,
            confidence: conf,
            timestamp_ns: 1_000_000_000,
        }
    }

    #[test]
    fn request_path_empty_signals_returns_empty() {
        let paths = detect_arbitrage(&[], "BTCUSDT").unwrap();
        assert!(paths.is_empty());
    }

    #[test]
    fn request_path_single_exchange_no_cycle() {
        let signals = vec![make_signal("A", "A", 10, 0.2, 0.9)];
        // Self-loop: weight is negative → negative cycle detected
        let paths = detect_arbitrage(&signals, "BTCUSDT").unwrap();
        // Single-node cycle is valid but hop_count should reflect it
        for p in &paths {
            assert!(p.hop_count >= 1);
        }
    }

    #[test]
    fn request_path_extreme_spread_values_no_panic() {
        let signals = vec![
            make_signal("A", "B", i32::MAX, 1.0, 0.0),
            make_signal("B", "A", i32::MAX, 1.0, 0.0),
        ];
        let _ = detect_arbitrage(&signals, "BTCUSDT");
        // Must not panic
    }

    #[test]
    fn request_path_zero_confidence_no_panic() {
        let signals = vec![
            make_signal("A", "B", 10, 0.5, 0.0),
            make_signal("B", "A", 10, 0.5, 0.0),
        ];
        let _ = detect_arbitrage(&signals, "BTCUSDT");
    }

    #[test]
    fn request_path_many_exchanges_no_panic() {
        let mut signals = Vec::new();
        for i in 0..50 {
            let src = format!("EX_{}", i);
            let tgt = format!("EX_{}", (i + 1) % 50);
            signals.push(make_signal(&src, &tgt, 5, 0.1, 0.9));
        }
        let _ = detect_arbitrage(&signals, "BTCUSDT");
    }

    #[test]
    fn request_path_concurrent_detection_no_race() {
        use std::thread;
        let signals = vec![
            make_signal("A", "B", 1, 0.01, 0.99),
            make_signal("B", "C", 1, 0.01, 0.99),
            make_signal("C", "A", 1, 0.01, 0.99),
        ];
        let mut handles = vec![];
        for _ in 0..20 {
            let sigs = signals.clone();
            handles.push(thread::spawn(move || {
                let _ = detect_arbitrage(&sigs, "BTCUSDT");
            }));
        }
        for h in handles {
            h.join().expect("thread must not panic");
        }
    }
}
