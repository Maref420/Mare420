use crate::gateway::BrokerGateway;
use crate::memory_events::{self, ExecutionOutcome, RiskAssessmentEvent};
use crate::types::Order;
use crate::validator::validate_order;
use atlas_risk_engine::circuit_breaker::CircuitBreaker;

#[derive(Debug, Clone, PartialEq)]
pub enum OrderStatus {
    PendingValidation,
    Validated,
    Rejected(Vec<String>),
    HaltedByCircuitBreaker,
    Submitted,
}

/// Convert a strategy signal into an Order.
///
/// This is the bridge between Strategy Engine signals and Execution Engine orders.
/// Takes raw fields (not DomainEvent) to avoid circular dependency.
/// Caller is responsible for extracting fields from DomainEvent.
///
/// Returns None if signal direction does not map to an order side (e.g., FLAT).
pub fn signal_to_order(
    event_id: uuid::Uuid,
    symbol: String,
    side: crate::types::OrderSide,
    quantity: f64,
    agent_id: String,
) -> Order {
    let now = chrono::Utc::now().to_rfc3339();
    Order {
        order_id: event_id,
        symbol,
        side,
        quantity,
        order_type: crate::types::OrderType::Market,
        price: None,
        stop_price: None,
        time_in_force: None,
        timestamp: now,
        agent_id,
        metadata: std::collections::HashMap::new(),
    }
}

pub struct OrderManager {
    gateway: Option<BrokerGateway>,
}

impl OrderManager {
    pub fn new() -> Self {
        Self { gateway: None }
    }

    /// Create an OrderManager with a broker gateway for memory event emission.
    pub fn with_gateway(gateway: BrokerGateway) -> Self {
        Self { gateway: Some(gateway) }
    }

    /// Validate order and check circuit breaker before admission.
    /// Emits memory experience events for operational tracking (fire-and-forget).
    pub fn admit_order(&self, order: &Order, breaker: &CircuitBreaker) -> OrderStatus {
        if breaker.is_halted() {
            tracing::warn!("Order {} blocked by circuit breaker", order.order_id);
            self.emit_risk_event(order, "circuit_breaker_check", "block", "tripped");
            return OrderStatus::HaltedByCircuitBreaker;
        }
        match validate_order(order) {
            Ok(()) => {
                tracing::info!("Order {} validated for {}", order.order_id, order.symbol);
                self.emit_execution_event(order, "validated");
                OrderStatus::Validated
            }
            Err(reasons) => {
                tracing::warn!("Order {} rejected: {:?}", order.order_id, reasons);
                self.emit_execution_event(order, "rejected");
                OrderStatus::Rejected(reasons)
            }
        }
    }

    /// Emit execution outcome event. Fire-and-forget: errors are logged, never propagated.
    fn emit_execution_event(&self, order: &Order, status: &str) {
        let Some(ref gw) = self.gateway else {
            tracing::debug!("No gateway configured, skipping memory event emission");
            return;
        };
        let outcome = ExecutionOutcome {
            order_id: order.order_id.to_string(),
            symbol: order.symbol.clone(),
            side: match order.side {
                crate::types::OrderSide::Buy => "buy".to_string(),
                crate::types::OrderSide::Sell => "sell".to_string(),
            },
            quantity: order.quantity,
            pnl: 0.0,
            status: status.to_string(),
        };
        if let Err(e) = memory_events::send_execution_outcome(gw, &outcome) {
            tracing::warn!(
                "Failed to emit execution outcome for order {}: {}",
                order.order_id, e
            );
        }
    }

    /// Emit risk assessment event. Fire-and-forget: errors are logged, never propagated.
    fn emit_risk_event(&self, order: &Order, assessment_type: &str, result: &str, cb_state: &str) {
        let Some(ref gw) = self.gateway else {
            tracing::debug!("No gateway configured, skipping memory event emission");
            return;
        };
        let assessment = RiskAssessmentEvent {
            assessment_type: assessment_type.to_string(),
            result: result.to_string(),
            circuit_breaker_state: cb_state.to_string(),
            risk_score: 100.0,
        };
        if let Err(e) = memory_events::send_risk_assessment(gw, &assessment) {
            tracing::warn!(
                "Failed to emit risk assessment for order {}: {}",
                order.order_id, e
            );
        }
    }
}
