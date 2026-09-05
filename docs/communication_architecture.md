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

---

## Memory Experience Event Pipeline

Version:
v1.0

Added:
2026-08-30

Architecture Review:
ARCH-REVIEW-002

### Data Flow

Rust Core Engine (Execution/Risk)
    |
    | EngineMessage envelope (memory.experience.v1)
    | Topic: memory.experience.v1
    v
Go Message Broker (Infrastructure)
    |
    | Envelope validation per memory-experience-event-v1.json
    | Channel transport / future NATS
    v
Python ExperienceEngine (AI Engine)
    |
    | MemoryKernel.store() → Episodic MemoryRecord
    v
Supabase (via MemoryStorage interface)

### Contract

Schema: contracts/schemas/memory/memory-experience-event-v1.json

Event Types:
- execution_outcome: Order execution results
- risk_assessment: Risk evaluation outcomes
- agent_decision: AI agent decision records

### Governance Compliance

- Dependency Rule: Rust → Infrastructure (Go) → Python (no direct Execution→AI)
- Module Ownership: Each module stays within responsibilities
- Audit: Every capture produces immutable audit event
- Validation: Triple-layer (Rust serialize + Go envelope + Python input)
