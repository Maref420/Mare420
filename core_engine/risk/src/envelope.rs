//! EngineMessage envelope types shared across Atlas crates.
//! Governed by: contracts/schemas/events/engine-contract-v1.json

use serde::{Deserialize, Serialize};

/// Message metadata per engine-contract-v1.json.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MessageMetadata {
    pub specification_id: String,
    pub policy_version: String,
    pub owner: String,
    pub validation_status: String,
}

/// Engine message envelope per engine-contract-v1.json.
/// Generic over payload type for type-safe serialization.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EngineMessage<T = serde_json::Value> {
    pub contract_version: String,
    pub message_type: String,
    pub source_engine: String,
    pub timestamp: String,
    pub payload: T,
    pub metadata: MessageMetadata,
}

impl<T: Serialize> EngineMessage<T> {
    /// Create a new risk/message envelope.
    pub fn new_risk_message(
        message_type: &str,
        specification_id: &str,
        payload: T,
    ) -> Self {
        let now = chrono::Utc::now().to_rfc3339();
        Self {
            contract_version: "1.0".to_string(),
            message_type: message_type.to_string(),
            source_engine: "rust_engine".to_string(),
            timestamp: now,
            payload,
            metadata: MessageMetadata {
                specification_id: specification_id.to_string(),
                policy_version: "1.0".to_string(),
                owner: "Risk Engine".to_string(),
                validation_status: "validated".to_string(),
            },
        }
    }
}
