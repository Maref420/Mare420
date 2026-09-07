// MODULE: atlas-memory-store
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: MemoryGraph engine with governed CRUD, TTL, keyword search.
use std::collections::HashMap;
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
        let found = st.nodes.get(id).map(|n| n.clone());
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
}
