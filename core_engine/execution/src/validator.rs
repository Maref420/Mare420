use crate::types::Order;
/// Pre-submission validation per order-v1.json rules.
/// Returns Ok(()) if order is valid, Err with list of violations.
pub fn validate_order(order: &Order) -> Result<(), Vec<String>> {
    order.validate()
}
