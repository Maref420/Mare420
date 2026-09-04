# ADR-008: Contract-First §17 Governance

**Date:** 2026-09-04
**Status:** Accepted
**Supersedes:** Inline restriction patterns in generator.py and llm_client.py

## Context

§17 restriction rules were duplicated across three files:
- `generator.py` → RESTRICTED_PATTERNS dict + _check_restrictions() method
- `llm_client.py` → RESTRICTED_CATEGORIES dict
- `restriction_guard.py` → CATEGORY_PATTERNS (source of truth)

This caused drift risk, maintenance burden, and violated the single source of truth principle.

## Decision

All §17 restriction rules extracted to a single JSON contract file:
`contracts/schemas/ai/restriction-rules-v1.json`

RestrictionGuard loads rules from this contract at startup. All other layers
(LLMClient, GeneratorEngine, Orchestrator) delegate to RestrictionGuard.

No layer may define its own restriction patterns inline.

## Consequences

### Positive
- Single source of truth for §17 rules
- Rule changes require editing only one JSON file
- Eliminates duplicate code (~150 lines removed)
- Machine-readable contract enables future tooling
- Aligns with CONSTITUTION.md §3 Policy Before Generation

### Negative
- RestrictionGuard now has filesystem dependency at import time
- JSON parse failure = empty rules (fail-safe but silent)

### Risks
- Contract file must be versioned and reviewed like code
- New categories require updating both JSON and RestrictionCategory enum

## Compliance

- ✅ CONSTITUTION.md §3: Policy Before Generation
- ✅ CONSTITUTION.md §3: Security First
- ✅ contracts/schemas/ai/ directory structure
- ✅ Regression tests verify enforcement unchanged
