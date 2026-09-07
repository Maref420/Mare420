// MODULE: atlas-feature-engine
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Matches Python ResearchAgent ForensicsSignal exactly.
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderbookLevel {
    pub price_scaled: i64,
    pub quantity: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TradeRecord {
    pub price_scaled: i64,
    pub quantity: f64,
    pub side: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketSnapshot {
    pub symbol: String,
    pub exchange: String,
    pub bids: Vec<OrderbookLevel>,
    pub asks: Vec<OrderbookLevel>,
    pub trades: Vec<TradeRecord>,
    pub timestamp_ns: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ForensicsSignal {
    pub symbol: String,
    pub raw_spread_bps: i32,
    pub aqs_score: i32,
    pub confidence: f64,
    pub orderbook_imbalance: f64,
    pub vpin_toxicity: f64,
    pub spoofing_detected: bool,
    pub trace_id: String,
    pub timestamp_ns: u64,
    pub source_uri: String,
}
