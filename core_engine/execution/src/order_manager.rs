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
pub struct OrderManager;
impl OrderManager {
    pub fn new() -> Self { Self }
    /// Validate order and check circuit breaker before admission.
    pub fn admit_order(&self, order: &Order, breaker: &CircuitBreaker) -> OrderStatus {
        if breaker.is_halted() {
            tracing::warn!("Order {} blocked by circuit breaker", order.order_id);
            return OrderStatus::HaltedByCircuitBreaker;
        }
        match validate_order(order) {
            Ok(()) => {
                tracing::info!("Order {} validated for {}", order.order_id, order.symbol);
                OrderStatus::Validated
            }
            Err(reasons) => {
                tracing::warn!("Order {} rejected: {:?}", order.order_id, reasons);
                OrderStatus::Rejected(reasons)
            }
        }
    }
}
