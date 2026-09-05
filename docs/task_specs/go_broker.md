# Go Broker — Task Specification

## Identity

- Module: services/message_broker/
- Language: Go
- Owner: platform_team
- Policy: governance/policies/go-policy.yaml

## Responsibility

Transport strategy signal messages between Python and Rust. Envelope validation.
Routing to NATS topic. NO business logic or payload modification.

## Input Contract

EngineMessage envelope with message_type: "strategy.signal.v1".
Payload: raw strategy-signal-event-v1 JSON.
Header fields: contract_version, source_engine, timestamp, metadata.

## Processing Rules

1. Envelope validation per engine-contract-v1.json
2. Payload validation per strategy-signal-event-v1.schema.json (to be implemented)
3. Route to NATS topic atlas.strategy.signal.v1
4. Preserve original payload byte-for-byte (no transformation)
5. Add broker metadata: receive timestamp, routing path

## Output / Side Effects

- NATS publish to atlas.strategy.signal.v1
- Broker metrics: message count, latency histogram

## Failure Behavior

- Invalid Envelope: reject + error response + audit log
- Invalid Payload: reject + error response + audit log
- NATS Connection Lost: buffer up to 1000 messages, then drop oldest
- Timeout (>5s): reject + error response

## Forbidden Actions

- Modify payload content
- Business logic or filtering based on signal content
- Store messages beyond buffer limit
- Expose internal routing metadata to consumers
- Allow unauthenticated publishers

## Dependencies

- <- intelligence/strategy_intelligence (Python producer)
- -> core_engine/strategy (Rust consumer)
- -> NATS cluster
- -> Audit Sink (rejection events)

## Acceptance Criteria

- Valid envelope + valid payload -> delivered to NATS
- Invalid envelope -> rejected before routing
- Payload preserved byte-for-byte
- Latency < 10ms p99
- Buffer overflow handled gracefully
