# Market Data Engine (`atlas-market-data`)

> ⚠️ **GOVERNED MODULE** — See header in `src/lib.rs` before modifying.

## Overview
Production-grade Rust library for deterministic, normalized market data processing.
All numeric values use scaled integers to ensure financial calculation accuracy.
Governed by `contracts/schemas/market/tick-data-v1.json`.

## Architecture & Data Flow

```text
Exchange WS/REST          Rust Engine              Consumers
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Go Adapter  │───▶│ atlas-market-data │───▶│ Risk Engine     │ (direct struct)
│ services/   │    │ core_engine/      │───▶│ Strategy Engine │ (direct struct)
│ exchanges/  │    │ market_data/      │───▶│ Analytics/Agents│ (FFI/gRPC)
└─────────────┘    └──────────────────┘    └─────────────────┘
                          │
                   Validates against
                   tick-data-v1.json
```

## Module Structure
| File | Purpose |
|------|---------|
| `src/lib.rs` | Public API surface, re-exports, Governance header |
| `src/types.rs` | `TickDataV1` struct, scaled integer types, `ErrorEnvelope` |

## Consumption Interface
| Consumer | Access Method | Contract | Policy |
|----------|--------------|----------|--------|
| Risk Engine | Direct Rust struct access | tick-data-v1 | Write: market_data only; Read: risk |
| Strategy Engine | Direct Rust struct access | tick-data-v1 | Write: market_data only; Read: strategy |
| Analytics / AI Agents | FFI/gRPC (scaled int → decimal) | ffi-boundary-v1 | Serialization rules enforced |

## Production Guarantees
- **Deterministic**: No floating-point types; all numerics are scaled integers
- **Immutable**: Tick objects are never mutated after creation
- **Monotonic**: Timestamp validation enforced at ingestion boundary
- **Bounded**: Metadata limited to 16 keys × 256 chars
- **Safe**: `unsafe_code = forbid`, `panic = deny`, `clippy = deny`
- **Error Handling**: Invalid ticks rejected with `ErrorEnvelope(code=TICK_INVALID, retryable=false)`

## Validation Commands
```bash
make validate-market-data    # Full governance compliance check
cargo clippy -- -D warnings  # Lint check only
cargo test                   # Unit + integration tests
```

## Governance References
| Artifact | Path |
|----------|------|
| Rust Policy | `governance/policies/rust-policy.yaml` |
| Market Data Contract | `contracts/schemas/market/tick-data-v1.json` |
| FFI Boundary Spec | `contracts/schemas/sdk/ffi-boundary-v1.json` |
| Module Ownership | `governance/ownership/module-ownership.yaml` |
| Architecture Lock | `governance/01_ARCHITECTURE_LOCK.md` |
