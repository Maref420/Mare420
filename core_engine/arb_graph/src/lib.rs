// MODULE: atlas-arb-graph
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Pure weighted directed graph + Bellman-Ford algorithm.
// WARNING: No unwrap/expect/panic on any path. All errors via Result.
pub mod bellman_ford;
pub mod graph;
pub mod mapper;

pub use bellman_ford::{find_negative_cycles, shortest_path, PathResult};
pub use graph::{GraphError, WeightedGraph};

#[cfg(test)]
mod request_path_tests {
    use super::*;

    #[test]
    fn request_path_large_graph_no_panic() {
        let names: Vec<String> = (0..100).map(|i| format!("N{}", i)).collect();
        let mut g = WeightedGraph::new(names);
        for i in 0..99 {
            let _ = g.add_edge(i, i + 1, 1.0);
        }
        let result = shortest_path(&g, 0, 99);
        assert!(result.is_ok());
        assert_eq!(result.unwrap().path.len(), 100);
    }

    #[test]
    fn request_path_extreme_weights_no_panic() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into(), "C".into()]);
        g.add_edge(0, 1, f64::MAX / 2.0).unwrap();
        g.add_edge(1, 2, f64::MAX / 2.0).unwrap();
        // Should not panic even with extreme weights
        let _ = shortest_path(&g, 0, 2);
    }

    #[test]
    fn request_path_nan_weight_handled() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into()]);
        g.add_edge(0, 1, f64::NAN).unwrap();
        // NaN comparisons are always false, so no relaxation happens
        let _ = shortest_path(&g, 0, 1);
        // Must not panic
    }

    #[test]
    fn request_path_self_loop_negative() {
        let mut g = WeightedGraph::new(vec!["A".into()]);
        g.add_edge(0, 0, -1.0).unwrap();
        let cycles = find_negative_cycles(&g);
        assert!(!cycles.is_empty(), "Self-loop with negative weight is a cycle");
    }

    #[test]
    fn request_path_concurrent_reads_no_race() {
        use std::thread;
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into(), "C".into()]);
        g.add_edge(0, 1, 1.0).unwrap();
        g.add_edge(1, 2, -3.0).unwrap();
        g.add_edge(2, 0, 1.0).unwrap();

        let mut handles = vec![];
        for _ in 0..20 {
            let g_clone = g.clone();
            handles.push(thread::spawn(move || {
                let _ = find_negative_cycles(&g_clone);
                let _ = shortest_path(&g_clone, 0, 2);
            }));
        }
        for h in handles {
            h.join().expect("thread must not panic");
        }
    }

    #[test]
    fn request_path_rapid_edge_updates_no_panic() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into(), "C".into()]);
        g.add_edge(0, 1, 1.0).unwrap();
        g.add_edge(1, 2, 1.0).unwrap();
        g.add_edge(2, 0, 1.0).unwrap();
        for i in 0..1000 {
            let w = if i % 2 == 0 { 1.0 } else { -2.0 };
            let _ = g.update_edge_weight(0, 1, w);
            let _ = find_negative_cycles(&g);
        }
    }
}
