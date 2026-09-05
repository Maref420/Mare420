# ADR-004: ExecutionOutcome Uses f64 (Temporary Exception)

## Status
Accepted | 2026-09-01 | Supersedes: None | To be superseded by: Phase 2 scaled-int migration

## Context
`ExecutionOutcome` struct in `core_engine/execution/src/memory_events.rs` uses
`f64` for `quantity` and `pnl` fields, while input DomainEvent uses scaled integers
(`quantity_scaled: u64`). This creates an internal inconsistency.

However, the downstream contract (`memory-experience-event-v1.json`) specifies
`"type": "number"` which permits floats. The Go Broker validator and Python
consumers currently accept float values.

## Decision
Temporarily accept f64 in ExecutionOutcome. Full migration to scaled integers
deferred to Phase 2 because:
1. Requires contract schema change (number → integer)
2. Requires Go Broker validator update
3. Requires Python consumer update
4. PnL calculation may inherently need fractional precision (under review)

## Action Items for Phase 2
- [ ] Evaluate if PnL can be represented as scaled integer
- [ ] Update memory-experience-event-v1.json schema
- [ ] Update Go Broker envelope validator
- [ ] Update Python memory system consumer
- [ ] Migrate ExecutionOutcome struct to u64

## Risks
- Non-deterministic PnL comparisons across runs
- Potential rounding errors in downstream analytics

## Related
- ADR-003: Execution Schemas Deterministic Migration
- core_engine/execution/src/memory_events.rs
- contracts/schemas/memory/memory-experience-event-v1.json
