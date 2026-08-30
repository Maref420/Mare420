# Atlas Strategy Engine

## Architecture (A+ Pattern)

Strict separation between cross-language contract types and internal domain types.

- contract_types.rs: 1:1 with schema, no business logic
- conversions.rs: Bridge Contract to Domain via TryFrom
- domain_types.rs: Internal execution, scaled integers (ADR-2026-08-30-004)

## Contract

- Schema: contracts/schemas/strategy/strategy-signal-event-v1.schema.json
- Envelope: contracts/events/strategy/strategy-signal-envelope-v1.md
- Version: 1.0.0

## Governance

- Owner: core_engine_team
- Policy: governance/policies/rust-policy.yaml
- Status: types_synced
- Approved Deps: serde, serde_json, thiserror, uuid

## Testing

    cd core_engine/strategy
    cargo test
    cargo clippy
