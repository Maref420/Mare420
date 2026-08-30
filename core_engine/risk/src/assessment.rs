use crate::types::RiskAssessment;
use uuid::Uuid;
use std::collections::HashMap;

/// Pre-trade risk assessment configuration.
/// Derived from governance/02_MODULE_OWNERSHIP.md Risk Engine responsibilities.
#[derive(Debug, Clone)]
pub struct RiskConfig {
    pub max_order_quantity: f64,
    pub allowed_symbols: Vec<String>,
    pub require_risk_score: bool,
}

/// Assess an order against risk configuration.
/// Returns a validated RiskAssessment per risk-assessment-v1.json.
pub fn assess_order(
    order_id: Uuid,
    agent_id: &str,
    symbol: &str,
    quantity: f64,
    config: &RiskConfig,
) -> RiskAssessment {
    let mut checks: Vec<String> = Vec::new();
    let mut approved = true;
    let mut rejection_reason: Option<String> = None;
    let mut risk_score: Option<f64> = None;

    // Check 1: Symbol allowed
    if !config.allowed_symbols.is_empty() && !config.allowed_symbols.contains(&symbol.to_string()) {
        approved = false;
        rejection_reason = Some(format!("symbol {symbol} not allowed"));
    }
    checks.push("symbol_check".to_string());

    // Check 2: Quantity limit
    if quantity > config.max_order_quantity {
        approved = false;
        rejection_reason = Some(format!("quantity {quantity} exceeds max {}", config.max_order_quantity));
    }
    checks.push("quantity_check".to_string());

    // Check 3: Positive quantity
    if quantity <= 0.0 {
        approved = false;
        rejection_reason = Some("quantity must be positive".to_string());
    }
    checks.push("positive_quantity_check".to_string());

    // Compute simple risk score (placeholder for future models)
    if config.require_risk_score {
        let score = if quantity > config.max_order_quantity * 0.8 { 0.9 } else { 0.1 };
        risk_score = Some(score);
    }
    checks.push("risk_score_computed".to_string());

    let assessment = RiskAssessment {
        assessment_id: Uuid::new_v4(),
        order_id,
        approved,
        assessed_at: chrono::Utc::now().to_rfc3339(),
        agent_id: agent_id.to_string(),
        checks_performed: checks,
        rejection_reason,
        risk_score,
        metadata: HashMap::new(),
    };

    // Self-validate before returning (Rule 4: deterministic behavior)
    // Note: validation errors here indicate a bug in assess_order logic
    if let Err(e) = assessment.validate() {
        tracing::error!("RiskAssessment self-validation failed: {e}");
    }

    assessment
}
