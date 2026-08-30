use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EngineMessage<T: Serialize> {
    pub contract_version: String,
    pub message_type: String,
    pub source_engine: String,
    pub timestamp: String,
    pub payload: T,
    pub metadata: MessageMetadata,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MessageMetadata {
    pub specification_id: String,
    pub policy_version: String,
    pub owner: String,
    pub validation_status: String,
}
impl<T: Serialize> EngineMessage<T> {
    pub fn new_risk_message(
        message_type: impl Into<String>,
        specification_id: impl Into<String>,
        payload: T,
    ) -> Self {
        Self {
            contract_version: "1.0".to_string(),
            message_type: message_type.into(),
            source_engine: "rust_engine".to_string(),
            timestamp: chrono::Utc::now().to_rfc3339(),
            payload,
            metadata: MessageMetadata {
                specification_id: specification_id.into(),
                policy_version: "1.0".to_string(),
                owner: "Risk Engine".to_string(),
                validation_status: "validated".to_string(),
            },
        }
    }
}
