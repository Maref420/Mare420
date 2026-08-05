# Atlas AI Module Ownership

## Module: Market Data Engine

Owner:
Rust Core

Language:
Rust

Responsibilities:
- Exchange websocket connections
- Orderbook processing
- Tick normalization
- Market data distribution

Forbidden:
- AI decisions
- ML inference
- Strategy learning


## Module: Strategy Engine

Owner:
Rust Core

Language:
Rust

Responsibilities:
- Signal generation
- Strategy execution logic
- Market condition evaluation

Forbidden:
- Model training
- AI reasoning


## Module: Risk Engine

Owner:
Rust Core

Language:
Rust

Responsibilities:
- Position limits
- Exposure control
- Risk validation
- Safety checks

Forbidden:
- Strategy creation
- AI model management


## Module: Execution Engine

Owner:
Rust Core

Language:
Rust

Responsibilities:
- Order management
- Exchange execution
- Trade lifecycle handling

Forbidden:
- Prediction
- Learning algorithms


## Module: AI Engine

Owner:
Python AI

Language:
Python

Responsibilities:
- Machine learning models
- Prediction systems
- Learning algorithms
- AI agents

Forbidden:
- Direct exchange execution
- Order placement


## Module: Analytics Engine

Owner:
Python AI

Language:
Python

Responsibilities:
- Market analysis
- Arbitrage analysis
- Backtesting
- Data intelligence

Forbidden:
- Low latency execution
- Exchange control


## Module: Contract Layer

Owner:
Shared

Language:
Rust/Python Compatible

Responsibilities:
- Event definitions
- Data schemas
- API contracts
- Module communication rules

Forbidden:
- Business logic
- Trading decisions


## Module: Infrastructure Layer

Owner:
Infrastructure

Language:
Depends on implementation

Responsibilities:
- Database
- Cache
- Message queues
- Monitoring
- Deployment

Forbidden:
- Business decisions
- Trading logic


## Module: Security Layer

Owner:
Security

Language:
Depends on implementation

Responsibilities:
- Authentication
- Encryption
- Key management
- Audit

Forbidden:
- Trading strategy logic
- AI decisions


## Module: Interface Layer

Owner:
Interfaces

Language:
Depends on implementation

Responsibilities:
- API
- Dashboard
- User interaction

Forbidden:
- Core business logic
- Direct database manipulation
