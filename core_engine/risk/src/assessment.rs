//! Risk Assessment: assess_order function.
//! Governed by: docs/task_specs/risk_engine.md

use crate::types::RiskAssessment;
use std::collections::HashMap;
use uuid::Uuid;

/// Configuration for order-level risk assessment.
#[derive(Debug, Clone)]
pub struct RiskConfig {
    pub max_order_quantity: f64,
    pub allowed_symbols: Vec<String>,
    pub require_risk_score: bool,
}

/// Assess an order and produce a RiskAssessment.
pub fn assess_order(
    order_id: Uuid,
    agent_id: &str,
    symbol: &str,
    quantity: f64,
    config: &RiskConfig,
) -> RiskAssessment {
    let mut checks = Vec::new();
    let mut rejection_reason: Option<String> = None;
    let mut approved = true;

    // Check 1: Symbol allowed
    if !config.allowed_symbols.is_empty() && !config.allowed_symbols.contains(&symbol.to_string()) {
        checks.push("symbol_check".to_string());
        approved = false;
        rejection_reason = Some(format!("symbol {symbol} not in allowed list"));
    } else {
        checks.push("symbol_check".to_string());
    }

    // Check 2: Quantity limit
    if quantity > config.max_order_quantity {
        checks.push("quantity_check".to_string());
        approved = false;
        rejection_reason = Some(format!(
            "quantity {quantity} exceeds max {}",
            config.max_order_quantity
        ));
    } else {
        checks.push("quantity_check".to_string());
    }

    // Risk score (simple heuristic)
    let risk_score = if config.require_risk_score {
        Some(0.5_f64) // placeholder heuristic
    } else {
        None
    };

    let now = chrono::Utc::now().to_rfc3339();

    RiskAssessment {
        assessment_id: Uuid::new_v4(),
        order_id,
        approved,
        assessed_at: now,
        agent_id: agent_id.to_string(),
        checks_performed: checks,
        rejection_reason,
        risk_score,
        metadata: HashMap::new(),
    }
}
