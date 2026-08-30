# Strategy Schemas

## strategy-signal-event-v1
- **Schema:** [strategy-signal-event-v1.schema.json](./strategy-signal-event-v1.schema.json)
- **Owner:** core_engine_team
- **Consumers:**
  - Producer: `intelligence/strategy_intelligence/` (Python)
  - Transport: `services/message_broker/` (Go) — validates envelope only
  - Consumer: `core_engine/strategy/` (Rust)
- **Lifecycle:** Market Regime Detection → Signal Generation → Validation → Broker Routing → Engine Processing
- **Versioning:** Semantic versioning in `$id` and `version` field
