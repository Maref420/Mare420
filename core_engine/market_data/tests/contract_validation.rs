use atlas_market_data::types::TickDataV1;
use serde_json;

#[test]
fn test_schema_validation_tick_data_v1() {
    let valid_json = r#"{
        "symbol": "BTCUSDT",
        "price_scaled": 100000000,
        "volume_scaled": 500,
        "timestamp_ns": 1700000000000000000,
        "exchange_id": "BINANCE",
        "bid_price_scaled": 99999999,
        "ask_price_scaled": 100000001,
        "trade_id": "12345",
        "metadata": {"source": "ws", "latency_us": "120"}
    }"#;

    let parsed: TickDataV1 = serde_json::from_str(valid_json)
        .expect("Valid tick-data-v1 must deserialize");
    assert!(parsed.validate().is_ok(), "Valid data must pass validation");
}

#[test]
fn test_schema_rejects_additional_properties() {
    let invalid_json = r#"{
        "symbol": "BTCUSDT",
        "price_scaled": 100000000,
        "volume_scaled": 500,
        "timestamp_ns": 1700000000000000000,
        "exchange_id": "BINANCE",
        "extra_field": "not_allowed"
    }"#;

    let result: Result<TickDataV1, _> = serde_json::from_str(invalid_json);
    assert!(result.is_err(), "additionalProperties=false must reject extra fields");
}
