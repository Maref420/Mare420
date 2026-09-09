// MODULE: atlas-arb-graph
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Bellman-Ford shortest path + negative cycle detection.
// WARNING: No unwrap/expect/panic. All functions return Result or safe defaults.
use serde::{Deserialize, Serialize};

use crate::graph::{GraphError, WeightedGraph};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PathResult {
    pub path: Vec<usize>,
    pub total_weight: f64,
}

/// Finds all negative-weight cycles reachable in the graph.
/// Uses Bellman-Ford with zero-initialized distances.
pub fn find_negative_cycles(graph: &WeightedGraph) -> Vec<PathResult> {
    let n = graph.node_count();
    if n == 0 {
        return Vec::new();
    }

    let edges = graph.edges();
    let mut dist = vec![0.0_f64; n];
    let mut parent: Vec<Option<usize>> = vec![None; n];

    // Relax V-1 times
    for _ in 0..n.saturating_sub(1) {
        let mut changed = false;
        for edge in edges {
            let new_dist = dist[edge.from] + edge.weight;
            if new_dist < dist[edge.to] - 1e-12 {
                dist[edge.to] = new_dist;
                parent[edge.to] = Some(edge.from);
                changed = true;
            }
        }
        if !changed {
            break;
        }
    }

    // Check for negative cycles (V-th relaxation)
    let mut cycles: Vec<PathResult> = Vec::new();
    let mut visited_in_cycle = vec![false; n];

    for edge in edges {
        let new_dist = dist[edge.from] + edge.weight;
        if new_dist < dist[edge.to] - 1e-12 {
            // Negative cycle detected — trace it back
            let mut cycle_start = edge.to;
            // Walk back n steps to ensure we're inside the cycle
            for _ in 0..n {
                if let Some(p) = parent[cycle_start] {
                    cycle_start = p;
                } else {
                    break;
                }
            }

            if visited_in_cycle[cycle_start] {
                continue;
            }

            // Trace the cycle
            let mut path = vec![cycle_start];
            let mut current = cycle_start;
            let mut total_weight = 0.0_f64;
            while let Some(p) = parent[current] {
                // Find edge weight
                let w = edges.iter()
                    .find(|e| e.from == p && e.to == current)
                    .map_or(0.0, |e| e.weight);
                total_weight += w;
                path.push(p);
                current = p;
                if current == cycle_start {
                    break;
                }
                if path.len() > n + 1 {
                    break; // Safety bound
                }
            }
            path.reverse();

            for &node in &path {
                visited_in_cycle[node] = true;
            }

            cycles.push(PathResult {
                path,
                total_weight,
            });
        }
    }

    cycles
}

/// Single-source shortest path using Bellman-Ford.
pub fn shortest_path(graph: &WeightedGraph, source: usize, target: usize) -> Result<PathResult, GraphError> {
    let n = graph.node_count();
    if n == 0 {
        return Err(GraphError::EmptyGraph);
    }
    if source >= n || target >= n {
        return Err(GraphError::InvalidNodeIndex {
            index: source.max(target),
            max: n.saturating_sub(1),
        });
    }

    let edges = graph.edges();
    let mut dist = vec![f64::INFINITY; n];
    let mut parent: Vec<Option<usize>> = vec![None; n];
    dist[source] = 0.0;

    for _ in 0..n.saturating_sub(1) {
        let mut changed = false;
        for edge in edges {
            if dist[edge.from] == f64::INFINITY {
                continue;
            }
            let new_dist = dist[edge.from] + edge.weight;
            if new_dist < dist[edge.to] - 1e-12 {
                dist[edge.to] = new_dist;
                parent[edge.to] = Some(edge.from);
                changed = true;
            }
        }
        if !changed {
            break;
        }
    }

    if dist[target] == f64::INFINITY {
        return Err(GraphError::EdgeNotFound { from: source, to: target });
    }

    // Reconstruct path
    let mut path = Vec::new();
    let mut current = target;
    while current != source {
        path.push(current);
        match parent[current] {
            Some(p) => current = p,
            None => return Err(GraphError::EdgeNotFound { from: source, to: target }),
        }
        if path.len() > n {
            return Err(GraphError::EdgeNotFound { from: source, to: target });
        }
    }
    path.push(source);
    path.reverse();

    Ok(PathResult {
        path,
        total_weight: dist[target],
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::graph::WeightedGraph;

    #[test]
    fn test_no_negative_cycle() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into(), "C".into()]);
        g.add_edge(0, 1, 1.0).unwrap();
        g.add_edge(1, 2, 2.0).unwrap();
        let cycles = find_negative_cycles(&g);
        assert!(cycles.is_empty());
    }

    #[test]
    fn test_simple_negative_cycle() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into(), "C".into()]);
        g.add_edge(0, 1, 1.0).unwrap();
        g.add_edge(1, 2, -3.0).unwrap();
        g.add_edge(2, 0, 1.0).unwrap();
        // Cycle: 0→1→2→0 = 1 + (-3) + 1 = -1 < 0
        let cycles = find_negative_cycles(&g);
        assert!(!cycles.is_empty(), "Expected negative cycle");
        assert!(cycles[0].total_weight < 0.0);
    }

    #[test]
    fn test_negative_cycle_4_nodes() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into(), "C".into(), "D".into()]);
        g.add_edge(0, 1, 1.0).unwrap();
        g.add_edge(1, 2, -2.0).unwrap();
        g.add_edge(2, 3, -1.0).unwrap();
        g.add_edge(3, 0, 1.0).unwrap();
        // Cycle: 0→1→2→3→0 = 1 + (-2) + (-1) + 1 = -1 < 0
        let cycles = find_negative_cycles(&g);
        assert!(!cycles.is_empty());
    }

    #[test]
    fn test_shortest_path_basic() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into(), "C".into()]);
        g.add_edge(0, 1, 2.0).unwrap();
        g.add_edge(1, 2, 3.0).unwrap();
        g.add_edge(0, 2, 10.0).unwrap();
        let result = shortest_path(&g, 0, 2).unwrap();
        assert_eq!(result.path, vec![0, 1, 2]);
        assert!((result.total_weight - 5.0).abs() < 1e-9);
    }

    #[test]
    fn test_shortest_path_no_path() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into(), "C".into()]);
        g.add_edge(0, 1, 1.0).unwrap();
        // No edge to node 2
        assert!(shortest_path(&g, 0, 2).is_err());
    }

    #[test]
    fn test_empty_graph() {
        let g = WeightedGraph::new(vec![]);
        assert!(shortest_path(&g, 0, 0).is_err());
        assert!(find_negative_cycles(&g).is_empty());
    }

    #[test]
    fn test_single_node() {
        let g = WeightedGraph::new(vec!["A".into()]);
        let result = shortest_path(&g, 0, 0).unwrap();
        assert_eq!(result.path, vec![0]);
        assert_eq!(result.total_weight, 0.0);
    }

    #[test]
    fn test_disconnected_components() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into(), "C".into(), "D".into()]);
        g.add_edge(0, 1, 1.0).unwrap();
        g.add_edge(2, 3, 1.0).unwrap();
        assert!(shortest_path(&g, 0, 3).is_err());
    }

    #[test]
    fn test_all_positive_no_cycle() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into(), "C".into()]);
        g.add_edge(0, 1, 5.0).unwrap();
        g.add_edge(1, 2, 5.0).unwrap();
        g.add_edge(2, 0, 5.0).unwrap();
        // Cycle: 0→1→2→0 = 15 > 0
        let cycles = find_negative_cycles(&g);
        assert!(cycles.is_empty());
    }

    #[test]
    fn test_serialization_roundtrip() {
        let result = PathResult { path: vec![0, 1, 2], total_weight: -1.5 };
        let json = serde_json::to_string(&result).expect("serialize");
        let parsed: PathResult = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(parsed.path, vec![0, 1, 2]);
        assert!((parsed.total_weight - (-1.5)).abs() < 1e-9);
    }
}
