// MODULE: atlas-memory-store
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: MemoryNode and MemoryEdge data structures per ADR-006.
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryNode {
    pub node_id: String,
    pub entity_type: String,
    pub attributes: HashMap<String, String>,
    pub source_uri: String,
    pub agent_id: String,
    pub ttl_ns: u64,
    pub created_at_ns: u64,
    pub updated_at_ns: u64,
}

impl MemoryNode {
    pub fn validate(&self) -> Result<(), MemoryError> {
        if self.node_id.is_empty() { return Err(MemoryError::InvalidNodeId); }
        if self.source_uri.is_empty() { return Err(MemoryError::MissingSourceBadge); }
        if self.agent_id.is_empty() { return Err(MemoryError::MissingAgentId); }
        if self.entity_type.is_empty() { return Err(MemoryError::InvalidEntityType); }
        Ok(())
    }

    pub fn is_expired(&self, now_ns: u64) -> bool {
        if self.ttl_ns == 0 { return false; }
        now_ns.saturating_sub(self.updated_at_ns) > self.ttl_ns
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEdge {
    pub from_node_id: String,
    pub to_node_id: String,
    pub relation: String,
    pub weight: f64,
    pub source_uri: String,
    pub agent_id: String,
    pub created_at_ns: u64,
}

impl MemoryEdge {
    pub fn validate(&self) -> Result<(), MemoryError> {
        if self.from_node_id.is_empty() || self.to_node_id.is_empty() {
            return Err(MemoryError::InvalidEdgeEndpoints);
        }
        if self.relation.is_empty() { return Err(MemoryError::InvalidRelation); }
        if self.source_uri.is_empty() { return Err(MemoryError::MissingSourceBadge); }
        if self.agent_id.is_empty() { return Err(MemoryError::MissingAgentId); }
        Ok(())
    }
}

#[derive(thiserror::Error, Debug)]
pub enum MemoryError {
    #[error("VAL_MISSING_SOURCE_BADGE: source_uri mandatory per ADR-006")]
    MissingSourceBadge,
    #[error("VAL_MISSING_AGENT_ID: agent_id mandatory per ADR-006")]
    MissingAgentId,
    #[error("VAL_INVALID_NODE_ID: node_id cannot be empty")]
    InvalidNodeId,
    #[error("VAL_INVALID_ENTITY_TYPE: entity_type cannot be empty")]
    InvalidEntityType,
    #[error("VAL_INVALID_EDGE: endpoints cannot be empty")]
    InvalidEdgeEndpoints,
    #[error("VAL_INVALID_RELATION: relation cannot be empty")]
    InvalidRelation,
    #[error("VAL_TTL_EXPIRED: node exceeded TTL")]
    TtlExpired,
    #[error("BIZ_CONFLICT_DETECTED: conflicting write")]
    ConflictDetected,
    #[error("DEP_STORE_UNAVAILABLE: {0}")]
    StoreUnavailable(String),
    #[error("INT_INVARIANT_BROKEN: {0}")]
    InternalError(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_node() -> MemoryNode {
        MemoryNode {
            node_id: "n1".into(), entity_type: "exchange".into(),
            attributes: HashMap::new(), source_uri: "test://v1".into(),
            agent_id: "a1".into(), ttl_ns: 3_600_000_000_000,
            created_at_ns: 1_000_000_000, updated_at_ns: 1_000_000_000,
        }
    }

    #[test] fn test_valid_passes() { assert!(valid_node().validate().is_ok()); }
    #[test] fn test_no_source_rejected() {
        let mut n = valid_node(); n.source_uri = "".into();
        assert!(matches!(n.validate().unwrap_err(), MemoryError::MissingSourceBadge));
    }
    #[test] fn test_no_agent_rejected() {
        let mut n = valid_node(); n.agent_id = "".into();
        assert!(matches!(n.validate().unwrap_err(), MemoryError::MissingAgentId));
    }
    #[test] fn test_ttl_not_expired() { assert!(!valid_node().is_expired(2_000_000_000)); }
    #[test] fn test_ttl_expired() {
        let mut n = valid_node(); n.ttl_ns = 500_000_000;
        assert!(n.is_expired(2_000_000_000));
    }
    #[test] fn test_zero_ttl_never_expires() {
        let mut n = valid_node(); n.ttl_ns = 0;
        assert!(!n.is_expired(u64::MAX));
    }
    #[test] fn test_serde_roundtrip() {
        let n = valid_node();
        let j = serde_json::to_string(&n).unwrap();
        let p: MemoryNode = serde_json::from_str(&j).unwrap();
        assert_eq!(p.node_id, "n1");
    }
}
