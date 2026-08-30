# Go Message Broker

> **Status:** partial | **Owner:** platform_team | **Language:** Go
> **Envelope Contract:** contracts/schemas/events/engine-contract-v1.json | **Policy:** governance/policies/go-policy.yaml

## Purpose

Transport messages between Python (Intelligence) and Rust (Engine) layers.
Validate envelopes, route to NATS topics, preserve payloads byte-for-byte.
NO business logic, NO payload modification.

## Architecture

    Python Producer
            |
            v
    +---------------------+
    | Envelope Validation | <-- engine-contract-v1.json
    | (envelope.go)       |     DisallowUnknownFields
    +----------+----------+
               |
               v
    +---------------------+
    | Payload Validation  | <-- Per message_type schema
    | (envelope.go)       |     strategy_signal: NOT YET IMPLEMENTED
    +----------+----------+
               |
               v
    +---------------------+
    | NATS Publisher      | <-- Route to topic by message_type
    | (main.go)           |     Buffer on disconnect (max 1000)
    +---------------------+

## Supported Message Types

| message_type | Payload Validation | Status |
|-------------|-------------------|--------|
| memory.experience.v1 | Full (execution_outcome, risk_assessment, agent_decision) | Implemented |
| strategy.signal.v1 | Header only (no payload validation) | Partial |
| market_update | None | Not implemented |
| system_status | None | Not implemented |

## Envelope Structure (EngineMessage)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| contract_version | string | Yes | Must be "1.0" |
| message_type | string | Yes | e.g., "strategy.signal.v1" |
| source_engine | string | Yes | rust_engine / python_engine / go_engine |
| timestamp | string | Yes | ISO 8601 |
| payload | json.RawMessage | Yes | Untouched payload |
| metadata.specification_id | string | Yes | Schema reference |
| metadata.policy_version | string | Yes | Policy version |
| metadata.owner | string | Yes | Module owner |
| metadata.validation_status | string | Yes | Validation result |

## Integration Guide

### Publishing a Strategy Signal

Wrap the strategy-signal-event-v1 JSON in an EngineMessage envelope:

    {
        "contract_version": "1.0",
        "message_type": "strategy.signal.v1",
        "source_engine": "python_engine",
        "timestamp": "2026-08-31T10:00:00Z",
        "payload": { ... strategy-signal-event-v1 JSON ... },
        "metadata": {
            "specification_id": "strategy-signal-event-v1",
            "policy_version": "1.0",
            "owner": "core_engine_team",
            "validation_status": "validated"
        }
    }

## Testing

    cd services/message_broker
    go test ./...

Existing test: internal/envelope/envelope_test.go

## Governance

| Artifact | Location |
|----------|----------|
| Main | services/message_broker/main.go |
| Envelope | services/message_broker/internal/envelope/envelope.go |
| Envelope Test | services/message_broker/internal/envelope/envelope_test.go |
| Contract | contracts/schemas/events/engine-contract-v1.json |
| Event Access Policy | configs/event-access-policy.yaml |

### Forbidden Actions

- Modify payload content
- Business logic or filtering based on signal content
- Store messages beyond buffer limit (1000)
- Expose internal routing metadata to consumers
- Allow unauthenticated publishers

## Known Gaps

| Gap | Impact | Priority |
|-----|--------|----------|
| strategy.signal.v1 payload validation not implemented | Invalid signals may pass | P1 |
| NATS connection not wired | Messages not delivered | P1 |
| No metrics collection | No observability | P2 |
| No authentication | Security gap | P2 |
