# Events Contracts

## Overview
Formalized event schemas for cross-language event-driven communication. All events are serialized as JSON and transported via Go Message Broker (`services/message_broker/`). Numeric fields use scaled integers per ADR-2026-08-30-004.

## Active Event Schemas
| Event | Version | Schema Path | Producer | Consumer |
|-------|---------|-------------|----------|----------|
| Memory Experience | v1 | `contracts/schemas/memory/memory-experience-event-v1.json` | Rust/Python | Python (ExperienceEngine) |
| Execution Outcome | v1 | `contracts/schemas/events/execution-outcome-event-v1.json` | Rust (Execution) | Python (MemorySubscriber), Go (Broker) |
| Risk Assessment | v1 | `contracts/schemas/events/risk-assessment-event-v1.json` | Rust (Risk Engine) | Python (MemorySubscriber), Go (Broker) |
| Agent Decision | v1 | `contracts/schemas/events/agent-decision-event-v1.json` | Python (AI Agents) | Python (MemorySubscriber), Go (Broker) |

## Data Flow (End-to-End)
1. **Producer** emits event as JSON conforming to schema
2. **Go Broker** validates against schema + routes to topic
3. **Consumer** deserializes and processes
4. **Audit** records event crossing boundary (ffi-boundary-v1.1)

## Sharing Interface
- **Transport**: Go Message Broker (gRPC/NATS)
- **Serialization**: JSON (deterministic, no floats)
- **Validation**: Schema enforcement at broker boundary
- **Access Policy**: Producers write-only, Consumers read-only

## Production Guarantees
- **Deterministic**: All numerics are scaled integers or basis points
- **Immutable**: Events are never mutated after emission
- **Bounded**: Metadata limited to 16 keys × 256 chars
- **Audited**: Every event crossing logged per ffi-boundary rules
- **Error Handling**: Invalid events rejected with ErrorEnvelope at broker
