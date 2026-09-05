/// PRODUCTION VALIDATION: Circuit Breaker actually blocks orders in realistic scenario.
#[test]
fn prod_breaker_blocks_valid_order_after_losses() {
    use atlas_risk_engine::circuit_breaker::{CircuitBreaker, TradeResult};
    use atlas_risk_engine::types::{CircuitBreakerConfig, HaltAction};
    use atlas_execution_engine::order_manager::{OrderManager, OrderStatus};
    use atlas_execution_engine::types::{Order, OrderSide, OrderType};
    use uuid::Uuid;
    use std::collections::HashMap;

    let config = CircuitBreakerConfig {
        max_consecutive_losses: 3,
        max_daily_loss_pct: 5.0,
        cooldown_seconds: 300,
        halt_action: HaltAction::StopNewOrders,
    };
    let mut cb = CircuitBreaker::new(config);
    let mgr = OrderManager::new();

    // Simulate 3 realistic losing trades with increasing magnitude
    let losses = [-150.0, -275.50, -420.0];
    for pnl in &losses {
        cb.record_trade(&TradeResult { pnl: *pnl });
    }
    assert!(cb.is_halted(), "breaker MUST trip after 3 consecutive losses");

    // Valid order MUST be blocked
    let order = Order {
        order_id: Uuid::new_v4(),
        symbol: "ETHUSDT".to_string(),
        side: OrderSide::Sell,
        quantity: 2.5,
        order_type: OrderType::Market,
        price: None, stop_price: None, time_in_force: None,
        timestamp: "2026-08-30T12:00:00Z".to_string(),
        agent_id: "prod-strategy-agent".to_string(),
        metadata: HashMap::new(),
    };
    assert_eq!(mgr.admit_order(&order, &cb), OrderStatus::HaltedByCircuitBreaker);

    // After reset, same order MUST pass
    cb.reset();
    assert_eq!(mgr.admit_order(&order, &cb), OrderStatus::Validated);
}

#[test]
fn prod_breaker_daily_loss_threshold_trips() {
    use atlas_risk_engine::circuit_breaker::{CircuitBreaker, TradeResult};
    use atlas_risk_engine::types::{CircuitBreakerConfig, HaltAction};
    let config = CircuitBreakerConfig {
        max_consecutive_losses: 100,
        max_daily_loss_pct: 2.0,
        cooldown_seconds: 60,
        halt_action: HaltAction::FullHalt,
    };
    let mut cb = CircuitBreaker::new(config);
    // Two trades that exceed daily loss threshold even without consecutive trigger
    cb.record_trade(&TradeResult { pnl: -1.5 });
    assert!(!cb.is_halted());
    cb.record_trade(&TradeResult { pnl: -0.6 });
    assert!(cb.is_halted(), "daily loss threshold MUST trip breaker");
}
