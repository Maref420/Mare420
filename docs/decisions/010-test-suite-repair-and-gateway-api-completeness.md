# ADR-010: Test Suite Repair & Gateway API Completeness

**Date:** 2026-09-04
**Status:** Accepted
**Depends on:** ADR-009 (Deployment Stage)

## Context

Full test suite had 7 failures blocking CI:
1. database_sink.py truncated (syntax error)
2. MemoryEventSubscriber renamed without test update
3. DeploymentRecord used deprecated Pydantic Config
4. ExperienceSubscriber missing _detect_event_type method
5. gateway.forget() missing explicit_policy_id passthrough
6. coding_loop test broken by Deployment Stage addition
7. e2e broker test fails without running infrastructure

## Decisions

### Production Code Fixes
- **gateway.forget()**: Added `explicit_policy_id` parameter passthrough
  to forgetting engine. This was an API completeness gap — gateway must
  expose all forgetting engine parameters per contract-first principles.
- **gateway.forget()**: Added REQUESTED/COMPLETED audit pair matching
  the pattern used by store() and retrieve(). Gateway is responsible for
  operation-level audit trail; engine handles internal lifecycle audits.
- **ExperienceSubscriber**: Added `_detect_event_type()` static method
  for event routing classification.
- **DeploymentRecord**: Migrated from deprecated `class Config` to
  `ConfigDict(frozen=True)` per Pydantic v2 requirements.

### Test Fixes
- coding_loop test: Mock deployer (unit tests must not depend on filesystem)
  and assert DEPLOYED status per §2 flow completion.
- gateway_memory_access test: Pass explicit_policy_id for SEMANTIC memory,
  expect 3 audit events (gateway-requested + engine-internal + gateway-completed).
- e2e_broker test: Skip when broker unavailable (infrastructure dependency).
- experience_engine test: Import alias for renamed class.

### Infrastructure Fix
- database_sink.py: Restored from last known good git revision (c2dfedd).
  File was truncated mid-docstring.

## Consequences

### Positive
- 154/155 tests pass (1 skipped = infrastructure dependency)
- Gateway API now complete for forgetting operations
- Audit trail consistent across all gateway operations
- Test suite validates §2 flow including deployment stage

### Negative
- None identified

### Future
- Contract schema validation tests for 27 uncovered contracts
- Broker e2e test should run in CI with broker container
