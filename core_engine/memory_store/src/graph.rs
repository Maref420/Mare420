// MODULE: atlas-memory-store
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: MemoryGraph engine with governed CRUD, TTL, keyword search,
//           temporal replay, causal trace, and diff capabilities.
use std::collections::{HashMap, HashSet, VecDeque};
use std::sync::RwLock;
use crate::node::{MemoryEdge, MemoryError, MemoryNode};

#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct MemoryStats {
    pub total_nodes: usize,
    pub total_edges: usize,
    pub stale_nodes: usize,
    pub enrichment_attempts: u64,
    pub enrichment_successes: u64,
    pub exception_count: u64,
}

impl MemoryStats {
    pub fn enrichment_rate(&self) -> f64 {
        if self.enrichment_attempts == 0 { return 1.0; }
        self.enrichment_successes as f64 / self.enrichment_attempts as f64
    }
    pub fn stale_percentage(&self) -> f64 {
        if self.total_nodes == 0 { return 0.0; }
        self.stale_nodes as f64 / self.total_nodes as f64
    }
}

#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
struct GraphState {
    nodes: HashMap<String, MemoryNode>,
    edges: Vec<MemoryEdge>,
    stats: MemoryStats,
}

pub struct MemoryGraph { state: RwLock<GraphState> }

impl MemoryGraph {
    pub fn new() -> Self { Self { state: RwLock::new(GraphState::default()) } }

    pub fn write_node(&self, node: MemoryNode) -> Result<(), MemoryError> {
        node.validate()?;
        let mut st = self.state.write().map_err(|e| MemoryError::InternalError(e.to_string()))?;
        if let Some(existing) = st.nodes.get(&node.node_id) {
            if node.updated_at_ns < existing.updated_at_ns {
                st.stats.exception_count += 1;
                return Err(MemoryError::ConflictDetected);
            }
        }
        st.nodes.insert(node.node_id.clone(), node);
        Ok(())
    }

    pub fn read_node(&self, id: &str, now_ns: u64) -> Result<Option<MemoryNode>, MemoryError> {
        let mut st = self.state.write().map_err(|e| MemoryError::InternalError(e.to_string()))?;
        st.stats.enrichment_attempts += 1;
        let found = st.nodes.get(id).cloned();
        match found {
            Some(n) => {
                if n.is_expired(now_ns) { return Err(MemoryError::TtlExpired); }
                st.stats.enrichment_successes += 1;
                Ok(Some(n))
            }
            None => Ok(None),
        }
    }

    pub fn add_edge(&self, edge: MemoryEdge) -> Result<(), MemoryError> {
        edge.validate()?;
        let mut st = self.state.write().map_err(|e| MemoryError::InternalError(e.to_string()))?;
        st.edges.push(edge);
        Ok(())
    }

    pub fn search(&self, keyword: &str, now_ns: u64) -> Result<Vec<MemoryNode>, MemoryError> {
        let st = self.state.read().map_err(|e| MemoryError::InternalError(e.to_string()))?;
        let kw = keyword.to_lowercase();
        Ok(st.nodes.values()
            .filter(|n| !n.is_expired(now_ns))
            .filter(|n| n.entity_type.to_lowercase().contains(&kw)
                || n.node_id.to_lowercase().contains(&kw)
                || n.attributes.values().any(|v| v.to_lowercase().contains(&kw)))
            .cloned().collect())
    }

    pub fn evict_expired(&self, now_ns: u64) -> Result<usize, MemoryError> {
        let mut st = self.state.write().map_err(|e| MemoryError::InternalError(e.to_string()))?;
        let before = st.nodes.len();
        st.nodes.retain(|_, n| !n.is_expired(now_ns));
        Ok(before - st.nodes.len())
    }

    pub fn stats(&self, now_ns: u64) -> Result<MemoryStats, MemoryError> {
        let st = self.state.read().map_err(|e| MemoryError::InternalError(e.to_string()))?;
        let mut s = st.stats.clone();
        s.total_nodes = st.nodes.len();
        s.total_edges = st.edges.len();
        s.stale_nodes = st.nodes.values().filter(|n| n.is_expired(now_ns)).count();
        Ok(s)
    }

    pub fn export_state(&self) -> Result<Vec<u8>, MemoryError> {
        let st = self.state.read().map_err(|e| MemoryError::StoreUnavailable(e.to_string()))?;
        serde_json::to_vec(&*st).map_err(|e| MemoryError::StoreUnavailable(e.to_string()))
    }

    pub fn import_state(&self, data: &[u8]) -> Result<(), MemoryError> {
        let imported: GraphState = serde_json::from_slice(data)
            .map_err(|e| MemoryError::StoreUnavailable(e.to_string()))?;
        let mut st = self.state.write().map_err(|e| MemoryError::InternalError(e.to_string()))?;
        *st = imported;
        Ok(())
    }

    pub fn node_count(&self) -> Result<usize, MemoryError> {
        let st = self.state.read().map_err(|e| MemoryError::InternalError(e.to_string()))?;
        Ok(st.nodes.len())
    }

    /// Reconstructs exact graph state at a given timestamp.
    /// Returns nodes alive at target_ns and edges where both endpoints are alive.
    pub fn replay_at(&self, target_ns: u64) -> Result<(Vec<MemoryNode>, Vec<MemoryEdge>), MemoryError> {
        let st = self.state.read().map_err(|e| MemoryError::InternalError(e.to_string()))?;
        let replayed_nodes: Vec<MemoryNode> = st.nodes.values()
            .filter(|n| n.created_at_ns <= target_ns && !n.is_expired(target_ns))
            .cloned()
            .collect();
        let node_ids: HashSet<String> = replayed_nodes.iter().map(|n| n.node_id.clone()).collect();
        let replayed_edges: Vec<MemoryEdge> = st.edges.iter()
            .filter(|e| node_ids.contains(&e.from_node_id) && node_ids.contains(&e.to_node_id))
            .cloned()
            .collect();
        Ok((replayed_nodes, replayed_edges))
    }

    /// BFS backward traversal from start_node following incoming edges.
    /// Max depth 10 to prevent cycles. Skips expired nodes.
    /// Returns chain ordered from start node to root cause ancestors.
    pub fn causal_trace(&self, start_node_id: &str, now_ns: u64) -> Result<Vec<MemoryNode>, MemoryError> {
        let st = self.state.read().map_err(|e| MemoryError::InternalError(e.to_string()))?;
        let mut visited = HashSet::new();
        let mut queue = VecDeque::new();
        let mut result = Vec::new();

        if let Some(start_node) = st.nodes.get(start_node_id) {
            if !start_node.is_expired(now_ns) {
                queue.push_back(start_node.clone());
                visited.insert(start_node_id.to_string());
            }
        }

        let mut depth = 0usize;
        while !queue.is_empty() && depth < 10 {
            let current_len = queue.len();
            for _ in 0..current_len {
                let node = match queue.pop_front() {
                    Some(n) => n,
                    None => break,
                };
                result.push(node.clone());
                for edge in &st.edges {
                    if edge.to_node_id == node.node_id {
                        let ancestor_id = &edge.from_node_id;
                        if !visited.contains(ancestor_id) {
                            if let Some(ancestor_node) = st.nodes.get(ancestor_id) {
                                if !ancestor_node.is_expired(now_ns) {
                                    visited.insert(ancestor_id.clone());
                                    queue.push_back(ancestor_node.clone());
                                }
                            }
                        }
                    }
                }
            }
            depth += 1;
        }
        Ok(result)
    }

    /// Computes (added, removed) nodes between two timestamps using replay_at.
    pub fn diff(&self, t1_ns: u64, t2_ns: u64) -> Result<(Vec<MemoryNode>, Vec<MemoryNode>), MemoryError> {
        let (nodes_t1, _) = self.replay_at(t1_ns)?;
        let (nodes_t2, _) = self.replay_at(t2_ns)?;
        let set_t1: HashSet<String> = nodes_t1.iter().map(|n| n.node_id.clone()).collect();
        let set_t2: HashSet<String> = nodes_t2.iter().map(|n| n.node_id.clone()).collect();
        let added: Vec<MemoryNode> = nodes_t2.into_iter()
            .filter(|n| !set_t1.contains(&n.node_id))
            .collect();
        let removed: Vec<MemoryNode> = nodes_t1.into_iter()
            .filter(|n| !set_t2.contains(&n.node_id))
            .collect();
        Ok((added, removed))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn mk(id: &str, ttl: u64, ts: u64) -> MemoryNode {
        MemoryNode { node_id: id.into(), entity_type: "test".into(),
            attributes: HashMap::new(), source_uri: "t://v1".into(),
            agent_id: "a1".into(), ttl_ns: ttl,
            created_at_ns: ts, updated_at_ns: ts }
    }

    #[test] fn test_write_read() {
        let g = MemoryGraph::new();
        g.write_node(mk("n1", 3_600_000_000_000, 1_000_000_000)).unwrap();
        assert!(g.read_node("n1", 2_000_000_000).unwrap().is_some());
    }

    #[test] fn test_no_source_rejected() {
        let g = MemoryGraph::new();
        let mut n = mk("n1", 0, 1); n.source_uri = "".into();
        assert!(g.write_node(n).is_err());
    }

    #[test] fn test_expired_read_fails() {
        let g = MemoryGraph::new();
        g.write_node(mk("n1", 500_000_000, 1_000_000_000)).unwrap();
        assert!(g.read_node("n1", 2_000_000_000).is_err());
    }

    #[test] fn test_conflict_rejected() {
        let g = MemoryGraph::new();
        g.write_node(mk("n1", 0, 2_000_000_000)).unwrap();
        assert!(g.write_node(mk("n1", 0, 1_000_000_000)).is_err());
    }

    #[test] fn test_evict() {
        let g = MemoryGraph::new();
        g.write_node(mk("n1", 500_000_000, 1_000_000_000)).unwrap();
        g.write_node(mk("n2", 0, 1_000_000_000)).unwrap();
        assert_eq!(g.evict_expired(2_000_000_000).unwrap(), 1);
        assert_eq!(g.node_count().unwrap(), 1);
    }

    #[test] fn test_search() {
        let g = MemoryGraph::new();
        let mut n = mk("bybit_status", 0, 1);
        n.entity_type = "exchange".into();
        n.attributes.insert("quality".into(), "DEGRADED".into());
        g.write_node(n).unwrap();
        assert_eq!(g.search("degraded", 2).unwrap().len(), 1);
        assert_eq!(g.search("nonexistent", 2).unwrap().len(), 0);
    }

    #[test] fn test_stats_enrichment_rate() {
        let g = MemoryGraph::new();
        g.write_node(mk("n1", 0, 1)).unwrap();
        let _ = g.read_node("n1", 2).unwrap();
        let _ = g.read_node("missing", 2).unwrap();
        let s = g.stats(2).unwrap();
        assert_eq!(s.enrichment_attempts, 2);
        assert_eq!(s.enrichment_successes, 1);
        assert!((s.enrichment_rate() - 0.5).abs() < 0.01);
    }

    #[test] fn test_export_import() {
        let g = MemoryGraph::new();
        g.write_node(mk("n1", 0, 1)).unwrap();
        let data = g.export_state().unwrap();
        let g2 = MemoryGraph::new();
        g2.import_state(&data).unwrap();
        assert_eq!(g2.node_count().unwrap(), 1);
    }

    #[test] fn test_concurrent_reads() {
        use std::thread;
        let g = std::sync::Arc::new(MemoryGraph::new());
        g.write_node(mk("n1", 0, 1)).unwrap();
        let mut handles = vec![];
        for _ in 0..20 {
            let gc = g.clone();
            handles.push(thread::spawn(move || { let _ = gc.read_node("n1", 2); }));
        }
        for h in handles { h.join().unwrap(); }
    }

    // === REPLAY TESTS ===

    #[test] fn test_replay_at_filters_by_time() {
        let g = MemoryGraph::new();
        g.write_node(mk("early", 0, 100)).unwrap();
        g.write_node(mk("mid", 0, 200)).unwrap();
        g.write_node(mk("late", 0, 300)).unwrap();

        let (nodes, _) = g.replay_at(250).unwrap();
        let ids: HashSet<String> = nodes.iter().map(|n| n.node_id.clone()).collect();
        assert!(ids.contains("early"));
        assert!(ids.contains("mid"));
        assert!(!ids.contains("late"));
    }

    #[test] fn test_replay_at_excludes_expired() {
        let g = MemoryGraph::new();
        g.write_node(mk("alive", 0, 100)).unwrap();
        g.write_node(mk("short_lived", 50, 100)).unwrap(); // expires at 150

        let (nodes, _) = g.replay_at(200).unwrap();
        let ids: HashSet<String> = nodes.iter().map(|n| n.node_id.clone()).collect();
        assert!(ids.contains("alive"));
        assert!(!ids.contains("short_lived"));
    }

    #[test] fn test_replay_at_filters_edges() {
        let g = MemoryGraph::new();
        g.write_node(mk("a", 0, 100)).unwrap();
        g.write_node(mk("b", 0, 200)).unwrap();
        g.write_node(mk("c", 0, 300)).unwrap();
        g.add_edge(MemoryEdge {
            from_node_id: "a".into(), to_node_id: "b".into(),
            relation: "uses".into(), weight: 1.0, source_uri: "t://v1".into(), agent_id: "a1".into(), created_at_ns: 200,
        }).unwrap();
        g.add_edge(MemoryEdge {
            from_node_id: "b".into(), to_node_id: "c".into(),
            relation: "uses".into(), weight: 1.0, source_uri: "t://v1".into(), agent_id: "a1".into(), created_at_ns: 300,
        }).unwrap();

        let (_, edges) = g.replay_at(250).unwrap();
        assert_eq!(edges.len(), 1); // only a→b, not b→c (c not alive at 250)
    }

    // === CAUSAL TRACE TESTS ===

    #[test] fn test_causal_trace_single_node() {
        let g = MemoryGraph::new();
        g.write_node(mk("lonely", 0, 100)).unwrap();
        let chain = g.causal_trace("lonely", 200).unwrap();
        assert_eq!(chain.len(), 1);
        assert_eq!(chain[0].node_id, "lonely");
    }

    #[test] fn test_causal_trace_follows_edges_backward() {
        let g = MemoryGraph::new();
        g.write_node(mk("root", 0, 100)).unwrap();
        g.write_node(mk("mid", 0, 200)).unwrap();
        g.write_node(mk("leaf", 0, 300)).unwrap();
        g.add_edge(MemoryEdge {
            from_node_id: "root".into(), to_node_id: "mid".into(),
            relation: "caused".into(), weight: 1.0, source_uri: "t://v1".into(), agent_id: "a1".into(), created_at_ns: 200,
        }).unwrap();
        g.add_edge(MemoryEdge {
            from_node_id: "mid".into(), to_node_id: "leaf".into(),
            relation: "caused".into(), weight: 1.0, source_uri: "t://v1".into(), agent_id: "a1".into(), created_at_ns: 300,
        }).unwrap();

        let chain = g.causal_trace("leaf", 400).unwrap();
        assert_eq!(chain.len(), 3);
        assert_eq!(chain[0].node_id, "leaf");
        assert_eq!(chain[1].node_id, "mid");
        assert_eq!(chain[2].node_id, "root");
    }

    #[test] fn test_causal_trace_skips_expired() {
        let g = MemoryGraph::new();
        g.write_node(mk("root", 50, 100)).unwrap(); // expires at 150
        g.write_node(mk("leaf", 0, 200)).unwrap();
        g.add_edge(MemoryEdge {
            from_node_id: "root".into(), to_node_id: "leaf".into(),
            relation: "caused".into(), weight: 1.0, source_uri: "t://v1".into(), agent_id: "a1".into(), created_at_ns: 200,
        }).unwrap();

        let chain = g.causal_trace("leaf", 300).unwrap();
        assert_eq!(chain.len(), 1); // root expired, only leaf
        assert_eq!(chain[0].node_id, "leaf");
    }

    #[test] fn test_causal_trace_nonexistent_returns_empty() {
        let g = MemoryGraph::new();
        let chain = g.causal_trace("ghost", 100).unwrap();
        assert!(chain.is_empty());
    }

    // === DIFF TESTS ===

    #[test] fn test_diff_added_nodes() {
        let g = MemoryGraph::new();
        g.write_node(mk("old", 0, 100)).unwrap();
        g.write_node(mk("new", 0, 300)).unwrap();

        let (added, removed) = g.diff(200, 400).unwrap();
        assert_eq!(added.len(), 1);
        assert_eq!(added[0].node_id, "new");
        assert!(removed.is_empty());
    }

    #[test] fn test_diff_removed_by_ttl() {
        let g = MemoryGraph::new();
        g.write_node(mk("persistent", 0, 100)).unwrap();
        g.write_node(mk("ephemeral", 50, 100)).unwrap(); // expires at 150

        let (added, removed) = g.diff(120, 200).unwrap();
        assert!(added.is_empty());
        assert_eq!(removed.len(), 1);
        assert_eq!(removed[0].node_id, "ephemeral");
    }

    #[test] fn test_diff_no_change() {
        let g = MemoryGraph::new();
        g.write_node(mk("stable", 0, 100)).unwrap();

        let (added, removed) = g.diff(200, 300).unwrap();
        assert!(added.is_empty());
        assert!(removed.is_empty());
    }
}


impl Default for MemoryGraph {
    fn default() -> Self { Self::new() }
}
