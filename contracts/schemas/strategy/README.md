# Strategy Schema

## Schema:
StrategySignal

Owner:
Rust Core

Producer:
Strategy Engine

Consumers:
- Risk Engine
- Execution Engine
- AI Engine
- Analytics Engine

Purpose:
Define validated strategy signal format used inside Atlas AI.

Fields:

timestamp:
Signal creation time

strategy_id:
Unique strategy identifier

symbol:
Trading pair identifier

signal_type:
Signal direction or action type

confidence:
Strategy confidence score

entry_price:
Suggested entry price

target_price:
Suggested target price

stop_loss:
Risk protection level

market_context:
Market condition metadata

Requirements:

- Strategy identity validation required
- Signal timestamp validation required
- Risk validation required before execution
- Schema versioning required

Forbidden:

- Direct exchange communication
- Direct order execution
- Risk bypass
- Unauthorized strategy modification

Version:

v0.1
