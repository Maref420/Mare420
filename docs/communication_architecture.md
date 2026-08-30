# Atlas AI Communication Architecture

Version:
v0.1

Purpose:
Define communication rules between Atlas AI system layers.

---

## Architecture Principle

Each layer communicates only through defined contracts.

Direct access between unrelated modules is forbidden.

---

## Communication Model

Rust Core:
Responsible for low-latency and safety-critical operations.

Python AI:
Responsible for intelligence, learning, and analysis.

Contract Layer:
Responsible for shared events and data schemas.

---

## Real-Time Communication

Path:

Rust Core
    |
    v
Contract Layer
    |
    v
Python AI


Use Cases:

- Market data updates
- Strategy analysis requests
- AI recommendations
- Risk notifications

---

## Event Communication

Producer:
Module generating an event

Consumer:
Module receiving an event

Rules:

- Events must follow defined schemas.
- Unknown event formats are rejected.
- Event versions must be tracked.
- All critical events must be auditable.

---

## Data Ownership

Rust Core Owns:

- Market data
- Strategy execution flow
- Risk decisions
- Trade execution


Python AI Owns:

- Models
- Predictions
- Learning processes
- Agent reasoning


Infrastructure Owns:

- Storage
- Message systems
- Monitoring

---

## Forbidden Communication

- AI directly accessing exchanges
- Strategy directly placing orders
- Modules bypassing contracts
- Direct database manipulation by business modules

---

## Security Requirements

- Authentication between services
- Permission validation
- Audit logging
- Data integrity validation

---

Version:
v0.1

## Risk Engine ↔ Execution Engine Boundary
- Contract: engine-contract-v1.json (shared envelope)
- Risk provides: RiskAssessment, KillSwitch, CircuitBreaker
- Execution consumes: CircuitBreaker.is_halted() as pre-admission gate
- Direction: Risk → Execution (read-only dependency via atlas-risk-engine crate)
- No reverse dependency: Execution MUST NOT call back into Risk internals
- Envelope re-use: Execution re-exports atlas_risk_engine::envelope (no duplication)
