# Market Data Schema

## Schema:
MarketTick

Owner:
Rust Core

Producer:
Market Data Engine

Consumers:
- Strategy Engine
- Risk Engine
- AI Engine
- Analytics Engine

Purpose:
Define normalized market data format used across Atlas AI.

Fields:

timestamp:
Event creation time

exchange:
Source exchange identifier

symbol:
Trading pair identifier

price:
Latest market price

volume:
Market volume information

bid:
Best bid price

ask:
Best ask price

spread:
Bid-ask difference

market_state:
Current market condition metadata

Requirements:

- Timestamp validation required
- Exchange source verification required
- Data normalization required
- Schema versioning required

Forbidden:

- Trading decisions
- Order execution data
- Private user information

Version:

v0.1
