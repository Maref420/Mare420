use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OrderSide { Buy, Sell }
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OrderType { Market, Limit, StopLimit, StopMarket }
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TimeInForce { Gtc, Ioc, Fok, Gtd }
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Order {
    pub order_id: Uuid,
    pub symbol: String,
    pub side: OrderSide,
    pub quantity: f64,
    pub order_type: OrderType,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub price: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stop_price: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub time_in_force: Option<TimeInForce>,
    pub timestamp: String,
    pub agent_id: String,
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}
impl Order {
    pub fn validate(&self) -> Result<(), Vec<String>> {
        let mut errors = Vec::new();
        if self.symbol.is_empty() {
            errors.push("symbol must not be empty".into());
        }
        if self.quantity <= 0.0 {
            errors.push("quantity must be > 0".into());
        }
        if self.agent_id.is_empty() {
            errors.push("agent_id must not be empty".into());
        }
        match self.order_type {
            OrderType::Limit | OrderType::StopLimit => {
                if self.price.is_none() || self.price.unwrap() <= 0.0 {
                    errors.push("price required and > 0 for limit orders".into());
                }
            }
            _ => {}
        }
        if errors.is_empty() { Ok(()) } else { Err(errors) }
    }
}
