use crate::types::Order;
use atlas_risk_engine::envelope::EngineMessage;

/// Gateway for sending orders to the Go Message Broker.
/// Uses ureq (sync HTTP). No async runtime required.
pub struct BrokerGateway {
    base_url: String,
}

impl BrokerGateway {
    pub fn new(base_url: impl Into<String>) -> Self {
        Self { base_url: base_url.into() }
    }

    /// Publish an order as an EngineMessage to the broker.
    pub fn publish_order(&self, order: &Order) -> Result<(), GatewayError> {
        let msg = EngineMessage::new_risk_message(
            "exec.order.v1",
            "order-v1",
            order.clone(),
        );
        let body = serde_json::to_vec(&msg)
            .map_err(|e| GatewayError::Serialization(e.to_string()))?;
        self.publish_raw(&body)
    }

    /// Publish pre-serialized bytes to the broker.
    /// Used by memory_events module for non-Order payloads.
    pub fn publish_raw(&self, body: &[u8]) -> Result<(), GatewayError> {
        let url = format!("{}/publish", self.base_url);
        let resp = ureq::post(&url)
            .set("Content-Type", "application/json")
            .send_bytes(body)
            .map_err(|e| GatewayError::Http(e.to_string()))?;
        if resp.status() != 200 {
            return Err(GatewayError::BrokerRejected(resp.status()));
        }
        tracing::info!("Event published to broker");
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum GatewayError {
    Serialization(String),
    Http(String),
    BrokerRejected(u16),
}

impl std::fmt::Display for GatewayError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            Self::Serialization(e) => write!(f, "serialization error: {e}"),
            Self::Http(e) => write!(f, "http error: {e}"),
            Self::BrokerRejected(s) => write!(f, "broker rejected with status {s}"),
        }
    }
}

impl std::error::Error for GatewayError {}
