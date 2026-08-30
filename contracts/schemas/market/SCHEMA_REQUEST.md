# Market Data Schema Request: tick-data-v1.json
## Status: PENDING ARCHITECT APPROVAL
## Requested By: Implementation Agent (Track A Complete)
## Priority: HIGH (blocks P1: Market Data Engine)
## Target: contracts/schemas/market/tick-data-v1.json

## Required Fields
| Field | Type | Constraint |
|-------|------|------------|
| symbol | string | min_length=1 |
| price | float | gt=0 |
| volume | float | ge=0 |
| timestamp_ns | int | gt=0, nanosecond precision |
| exchange_id | string | min_length=1 |

## Optional Fields
| Field | Type |
|-------|------|
| bid_price | float(gt=0) or null |
| ask_price | float(gt=0) or null |
| trade_id | string or null |
| metadata | dict[string,any] default={} |

## Rules
- extra_fields: forbid
- immutable_after_creation: true
- timestamp_monotonic: true (within same symbol stream)

## Consumers
- Risk Engine (price/volume validation)
- Strategy Engine (signal generation)
- Analytics Engine (market analysis)

## Architect Action
Review, modify if needed, approve, and create file at target path.
