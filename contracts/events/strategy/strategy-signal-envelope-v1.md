# Strategy Signal Event Envelope — v1

## Routing
- **Producer:** `intelligence/strategy_intelligence/` (Python)
- **Transport:** `services/message_broker/` (Go) — validates envelope header only
- **Consumer:** `core_engine/strategy/` (Rust)

## Topic
`atlas.strategy.signal.v1`

## Sample Payload
```json
{
  "version": "1.0.0",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp_utc": "2026-08-31T10:00:00Z",
  "trace_id": "660e8400-e29b-41d4-a716-446655440001",
  "source_agent": "strategy_selector_v2",
  "signal": {
    "symbol": "BTCUSDT",
    "direction": "LONG",
    "confidence": 0.87,
    "regime": "TRENDING",
    "parameters": {}
  },
  "metadata": {}
}
```

## Validation Rules
- All fields in `required` MUST be present
- `additionalProperties: false` — no extra fields allowed
- `confidence` range: [0.0, 1.0]
- `symbol` pattern: `^[A-Z0-9]{2,20}$`
