use crate::types::Order;
/// Exchange connector interface per governance/02_MODULE_OWNERSHIP.md.
/// Implementations handle exchange-specific protocol details.
/// Forbidden: business logic, strategy, AI inference.
pub trait ExchangeConnector: Send + Sync {
    /// Submit an order to the exchange. Returns exchange order ID.
    fn submit_order(&self, order: &Order) -> Result<String, ConnectorError>;
    /// Cancel an order by exchange order ID.
    fn cancel_order(&self, exchange_order_id: &str) -> Result<(), ConnectorError>;
    /// Check if the connector is connected and ready.
    fn is_ready(&self) -> bool;
}
#[derive(Debug, Clone, PartialEq)]
pub enum ConnectorError {
    ConnectionLost,
    OrderRejected(String),
    Timeout,
    Internal(String),
}
impl std::fmt::Display for ConnectorError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            Self::ConnectionLost => write!(f, "connection lost"),
            Self::OrderRejected(r) => write!(f, "order rejected: {r}"),
            Self::Timeout => write!(f, "request timeout"),
            Self::Internal(e) => write!(f, "internal error: {e}"),
        }
    }
}
impl std::error::Error for ConnectorError {}
/// Mock connector for testing. Records submitted orders.
pub struct MockConnector {
    pub submitted: std::sync::Mutex<Vec<Order>>,
    pub ready: bool,
}
impl MockConnector {
    pub fn new(ready: bool) -> Self {
        Self { submitted: std::sync::Mutex::new(Vec::new()), ready }
    }
}
impl ExchangeConnector for MockConnector {
    fn submit_order(&self, order: &Order) -> Result<String, ConnectorError> {
        if !self.ready { return Err(ConnectorError::ConnectionLost); }
        let id = format!("MOCK-{}", order.order_id);
        self.submitted.lock().map_err(|e| ConnectorError::Internal(e.to_string()))?.push(order.clone());
        tracing::info!("MockConnector: submitted order {id}");
        Ok(id)
    }
    fn cancel_order(&self, exchange_order_id: &str) -> Result<(), ConnectorError> {
        if !self.ready { return Err(ConnectorError::ConnectionLost); }
        tracing::info!("MockConnector: cancelled {exchange_order_id}");
        Ok(())
    }
    fn is_ready(&self) -> bool { self.ready }
}
