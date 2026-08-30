use atlas_execution_engine::types::{Order, OrderSide, OrderType};
use atlas_execution_engine::order_manager::{OrderManager, OrderStatus};
use uuid::Uuid;
use std::collections::HashMap;

fn make_valid_order() -> Order {
    Order {
        order_id: Uuid::new_v4(),
        symbol: "BTCUSDT".to_string(),
        side: OrderSide::Buy,
        quantity: 1.5,
        order_type: OrderType::Market,
        price: None,
        stop_price: None,
        time_in_force: None,
        timestamp: "2026-08-30T00:00:00Z".to_string(),
        agent_id: "test-agent".to_string(),
        metadata: HashMap::new(),
    }
}
#[test]
fn order_json_roundtrip() {
    let order = make_valid_order();
    let json = serde_json::to_string(&order).expect("serialize failed");
    let deserialized: Order = serde_json::from_str(&json).expect("deserialize failed");
    assert_eq!(order, deserialized);
}
#[test]
fn unknown_fields_rejected() {
    let json = r#"{"order_id":"00000000-0000-0000-0000-000000000000","symbol":"BTC","side":"buy","quantity":1.0,"order_type":"market","timestamp":"2026-01-01T00:00:00Z","agent_id":"a","bad_field":true}"#;
    let result: Result<Order, _> = serde_json::from_str(json);
    assert!(result.is_err(), "unknown fields must be rejected");
}
#[test]
fn limit_order_requires_price() {
    let mut order = make_valid_order();
    order.order_type = OrderType::Limit;
    order.price = None;
    assert!(order.validate().is_err());
}
#[test]
fn limit_order_with_valid_price_passes() {
    let mut order = make_valid_order();
    order.order_type = OrderType::Limit;
    order.price = Some(67000.0);
    assert!(order.validate().is_ok());
}
#[test]
fn zero_quantity_rejected() {
    let mut order = make_valid_order();
    order.quantity = 0.0;
    assert!(order.validate().is_err());
}
#[test]
fn empty_symbol_rejected() {
    let mut order = make_valid_order();
    order.symbol = String::new();
    assert!(order.validate().is_err());
}
#[test]
fn admit_order_valid_returns_validated() {
    let mgr = OrderManager::new();
    let order = make_valid_order();
    let cb = atlas_risk_engine::circuit_breaker::CircuitBreaker::new(atlas_risk_engine::types::CircuitBreakerConfig { max_consecutive_losses: 10, max_daily_loss_pct: 100.0, cooldown_seconds: 60, halt_action: atlas_risk_engine::types::HaltAction::FullHalt });
    let status = mgr.admit_order(&order, &cb);
    assert_eq!(status, OrderStatus::Validated);
}
#[test]
fn admit_order_invalid_returns_rejected() {
    let mgr = OrderManager::new();
    let mut order = make_valid_order();
    order.quantity = -1.0;
    let cb2 = atlas_risk_engine::circuit_breaker::CircuitBreaker::new(atlas_risk_engine::types::CircuitBreakerConfig { max_consecutive_losses: 10, max_daily_loss_pct: 100.0, cooldown_seconds: 60, halt_action: atlas_risk_engine::types::HaltAction::FullHalt });
    match mgr.admit_order(&order, &cb2) {
        OrderStatus::Rejected(reasons) => {
            assert!(!reasons.is_empty());
        }
        other => panic!("expected Rejected, got {:?}", other),
    }
}
#[test]
fn envelope_reexport_works() {
    use atlas_execution_engine::envelope::EngineMessage;
    let order = make_valid_order();
    let msg = EngineMessage::new_risk_message("exec.order.v1", "order-v1", order);
    assert_eq!(msg.contract_version, "1.0");
    assert_eq!(msg.source_engine, "rust_engine");
}
#[test]
fn admit_order_blocked_by_circuit_breaker() {
    use atlas_risk_engine::circuit_breaker::{CircuitBreaker, TradeResult};
    use atlas_risk_engine::types::{CircuitBreakerConfig, HaltAction};
    let config = CircuitBreakerConfig { max_consecutive_losses: 1, max_daily_loss_pct: 100.0, cooldown_seconds: 60, halt_action: HaltAction::FullHalt };
    let mut cb = CircuitBreaker::new(config);
    cb.record_trade(&TradeResult { pnl: -1.0 });
    assert!(cb.is_halted());
    let mgr = OrderManager::new();
    let order = make_valid_order();
    let status = mgr.admit_order(&order, &cb);
    assert_eq!(status, OrderStatus::HaltedByCircuitBreaker);
}
#[test]
fn mock_connector_submits_order() {
    use atlas_execution_engine::connector::{ExchangeConnector, MockConnector};
    let connector = MockConnector::new(true);
    let order = make_valid_order();
    let result = connector.submit_order(&order);
    assert!(result.is_ok());
    assert!(result.unwrap().starts_with("MOCK-"));
    assert_eq!(connector.submitted.lock().unwrap().len(), 1);
}
#[test]
fn mock_connector_rejects_when_not_ready() {
    use atlas_execution_engine::connector::{ExchangeConnector, MockConnector, ConnectorError};
    let connector = MockConnector::new(false);
    let order = make_valid_order();
    let result = connector.submit_order(&order);
    assert_eq!(result, Err(ConnectorError::ConnectionLost));
}
#[test]
fn mock_connector_cancel_works() {
    use atlas_execution_engine::connector::{ExchangeConnector, MockConnector};
    let connector = MockConnector::new(true);
    assert!(connector.cancel_order("MOCK-123").is_ok());
}


#[test]
fn test_signal_to_order_creates_valid_market_order() {
    use atlas_execution_engine::order_manager::signal_to_order;
    use atlas_execution_engine::types::OrderSide;
    use uuid::Uuid;

    let event_id = Uuid::new_v4();
    let order = signal_to_order(
        event_id,
        "BTCUSDT".to_string(),
        OrderSide::Buy,
        1.5,
        "strategy_agent".to_string(),
    );

    assert_eq!(order.order_id, event_id);
    assert_eq!(order.symbol, "BTCUSDT");
    assert_eq!(order.side, OrderSide::Buy);
    assert_eq!(order.quantity, 1.5);
    assert_eq!(order.agent_id, "strategy_agent");
    assert_eq!(order.order_type, atlas_execution_engine::types::OrderType::Market);
    assert!(order.price.is_none());
    // Must pass validation
    assert!(order.validate().is_ok());
}

#[test]
fn test_signal_to_order_preserves_event_id_for_traceability() {
    use atlas_execution_engine::order_manager::signal_to_order;
    use atlas_execution_engine::types::OrderSide;
    use uuid::Uuid;

    let original_event_id = Uuid::parse_str("550e8400-e29b-41d4-a716-446655440000").unwrap();
    let order = signal_to_order(
        original_event_id,
        "ETHUSDT".to_string(),
        OrderSide::Sell,
        10.0,
        "momentum_v3".to_string(),
    );

    assert_eq!(order.order_id, original_event_id);
}
