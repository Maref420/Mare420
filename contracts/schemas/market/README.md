# Market Data Contracts

## Overview
Deterministic, production-grade schemas for normalized market data across all supported exchanges. All numeric values use scaled integers to ensure financial calculation accuracy and compliance with `governance/policies/rust-policy.yaml`.

## Active Contracts
| Contract | Version | Status | Owner |
|----------|---------|--------|-------|
| tick-data | v1 | ✅ Approved | core_engine/market_data (Rust) |

## Data Flow (End-to-End)
1. **Ingestion**: Exchange WS/REST → Go Adapter (`services/exchanges/{name}/`)
2. **Normalization**: Raw feed → Rust Market Data Engine (`core_engine/market_data/`)
3. **Validation**: Against `tick-data-v1.json` schema (boundary test enforced)
4. **Distribution**:
   - Risk/Strategy Engines: Direct Rust struct access
   - Analytics/Agents: Via FFI/gRPC with scaled int → decimal conversion

## Sharing Interface
- **Consumed**: Raw exchange feeds (Go layer, non-contract)
- **Exposed**: `TickDataV1` Rust struct, `tick_data_v1_pb` Protobuf
- **Access Policy**: Write-only by Market Data Engine; Read-only by Risk/Strategy/Analytics
- **FFI Boundary**: Serialization rules in `contracts/schemas/sdk/ffi-boundary-v1.json`

## Production Guarantees
- **Deterministic**: No floating-point types; all numerics are scaled integers
- **Immutable**: Tick objects are never mutated after creation
- **Monotonic**: Timestamp validation enforced at ingestion boundary
- **Bounded**: Metadata limited to 16 keys × 256 chars to prevent uncontrolled memory growth
- **Error Handling**: Invalid ticks rejected with `ErrorEnvelope(code=TICK_INVALID, retryable=false, service=market_data)`
