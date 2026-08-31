# ADR-003: Execution Schemas Deterministic Migration (float → scaled integer)

## Status
Accepted | 2026-09-01

## Context
Execution schemas (`order-v1.json`, `circuit-breaker-v1.json`) originally used
`float` types for numeric fields (quantity, price, stop_price, max_daily_loss_pct).
This violated the deterministic processing principle established in market_data
and rust-policy.yaml.

## Decision
Migrated all numeric fields from float to scaled integer:
- `quantity`: float(gt=0) → integer(gt=0) [scaled to smallest asset unit]
- `price`: float(gt=0)|null → integer(gt=0)|null [scaled to smallest currency unit]
- `stop_price`: float(gt=0)|null → integer(gt=0)|null
- `max_daily_loss_pct`: float(gt=0,le=100) → integer(gt=0,le=10000) [basis points]

Schema version bumped: 1.0 → 1.1 with full migration metadata.

## Consequences
- ✅ All execution schemas now deterministic (no floating-point)
- ✅ Consistent with market_data and risk_engine conventions
- ⚠️ ExecutionOutcome Rust struct still uses f64 (see ADR-004)
- 🔒 Pre-migration backups (.bak.pre-deterministic.*) deleted as untracked artifacts

## Related
- ADR-002: .bak Files Disposal (core_engine/market_data)
- contracts/schemas/execution/order-v1.json (v1.1)
- contracts/schemas/execution/circuit-breaker-v1.json (v1.1)
