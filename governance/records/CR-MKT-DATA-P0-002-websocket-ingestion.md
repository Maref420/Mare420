# Governance Record

## Change ID
CR-MKT-DATA-P0-002

## Title
WebSocket Ingestion Module Scaffold and Architecture Decision

## Status
Implemented (Scaffold Only - Business Logic Pending)

## Summary
Established architecture for market data WebSocket ingestion per Matrix B.
Created ADR-006 defining Go ownership, Unix Domain Socket IPC, and binary protocol.
Scaffolded services/ingestion/ module with README, test skeletons, and Makefile targets.
No business logic implemented yet; TDD approach enforced.

## Governance Alignment
- No governance rules changed
- Integrated with existing Matrix B, Contract, and Testing policies
- No parallel path introduced
- Dead dependency (Python websockets) flagged for removal

## Affected Modules
- services/ingestion (NEW)
- core_engine/market_data (future: IPC listener)

## Affected Contracts
- IPC Binary Format v1 (new, defined in ADR-006)
- tick-data-v1.json (unchanged, consumed downstream)

## Languages
- Go (new module)
- Rust (future IPC listener)

## Compatibility
- Backward-compatible: YES (new module, no existing behavior changed)
- Breaking changes: NONE

## Testing Evidence
- Test skeletons created (contract, config validation, backpressure)
- Golden dataset structure established
- Full test suite pending business logic implementation

## Rollback Plan
Remove services/ingestion/ directory and revert Makefile additions.
No existing functionality affected.

## Related ADRs
- ADR-006: WebSocket Ingestion Architecture
- CR-MKT-DATA-P0-001: Phase 1 Market Data Stabilization
