// MODULE: atlas-arb-graph
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Pure weighted directed graph data structure.
// WARNING: No unwrap/expect/panic. All operations return Result.
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum GraphError {
    #[error("invalid node index {index}, max is {max}")]
    InvalidNodeIndex { index: usize, max: usize },
    #[error("edge not found: {from} -> {to}")]
    EdgeNotFound { from: usize, to: usize },
    #[error("empty graph")]
    EmptyGraph,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Edge {
    pub from: usize,
    pub to: usize,
    pub weight: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WeightedGraph {
    nodes: Vec<String>,
    edges: Vec<Edge>,
}

impl WeightedGraph {
    pub fn new(node_names: Vec<String>) -> Self {
        Self {
            nodes: node_names,
            edges: Vec::new(),
        }
    }

    pub fn node_count(&self) -> usize {
        self.nodes.len()
    }

    pub fn edge_count(&self) -> usize {
        self.edges.len()
    }

    pub fn add_edge(&mut self, from: usize, to: usize, weight: f64) -> Result<(), GraphError> {
        if from >= self.nodes.len() {
            return Err(GraphError::InvalidNodeIndex { index: from, max: self.nodes.len().saturating_sub(1) });
        }
        if to >= self.nodes.len() {
            return Err(GraphError::InvalidNodeIndex { index: to, max: self.nodes.len().saturating_sub(1) });
        }
        self.edges.push(Edge { from, to, weight });
        Ok(())
    }

    pub fn update_edge_weight(&mut self, from: usize, to: usize, new_weight: f64) -> Result<(), GraphError> {
        for edge in &mut self.edges {
            if edge.from == from && edge.to == to {
                edge.weight = new_weight;
                return Ok(());
            }
        }
        Err(GraphError::EdgeNotFound { from, to })
    }

    pub fn get_node_name(&self, idx: usize) -> Option<&str> {
        self.nodes.get(idx).map(|s| s.as_str())
    }

    pub fn clear_edges(&mut self) {
        self.edges.clear();
    }

    pub fn edges(&self) -> &[Edge] {
        &self.edges
    }

    pub fn nodes(&self) -> &[String] {
        &self.nodes
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_graph() {
        let g = WeightedGraph::new(vec!["A".into(), "B".into(), "C".into()]);
        assert_eq!(g.node_count(), 3);
        assert_eq!(g.edge_count(), 0);
    }

    #[test]
    fn test_add_edge_valid() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into()]);
        assert!(g.add_edge(0, 1, 1.5).is_ok());
        assert_eq!(g.edge_count(), 1);
    }

    #[test]
    fn test_add_edge_invalid_index() {
        let mut g = WeightedGraph::new(vec!["A".into()]);
        assert!(g.add_edge(0, 5, 1.0).is_err());
        assert!(g.add_edge(5, 0, 1.0).is_err());
    }

    #[test]
    fn test_update_edge_weight() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into()]);
        g.add_edge(0, 1, 1.0).unwrap();
        assert!(g.update_edge_weight(0, 1, 2.5).is_ok());
        assert_eq!(g.edges()[0].weight, 2.5);
    }

    #[test]
    fn test_update_nonexistent_edge() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into()]);
        assert!(g.update_edge_weight(0, 1, 1.0).is_err());
    }

    #[test]
    fn test_clear_edges() {
        let mut g = WeightedGraph::new(vec!["A".into(), "B".into()]);
        g.add_edge(0, 1, 1.0).unwrap();
        g.clear_edges();
        assert_eq!(g.edge_count(), 0);
        assert_eq!(g.node_count(), 2);
    }

    #[test]
    fn test_get_node_name() {
        let g = WeightedGraph::new(vec!["alpha".into(), "beta".into()]);
        assert_eq!(g.get_node_name(0), Some("alpha"));
        assert_eq!(g.get_node_name(1), Some("beta"));
        assert_eq!(g.get_node_name(5), None);
    }
}
