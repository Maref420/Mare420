# ADR 006: Governed Memory System Architecture

## Status
Proposed (Pending Human Owner Approval per R02)

## Context (R01 — Real Need)
Atlas-AI agents lack persistent, governed memory. Each session starts from zero.
Corrections evaporate. Knowledge doesn't transfer between agents.
This causes duplicate work, inconsistent decisions, and no audit trail.

Pain point: Marketing analyst manually re-explains company terminology every session.
Scorecard need: Measure accuracy, adoption, hours saved, AND exception rate.

## Decision
1. Substrate: Local JSON (Phase 1) → Rust-backed store (Phase 2)
2. Enrichment: Via `atlas_agent.LLMClient` only (cache + guard + circuit-breaker)
3. Provenance (R03): `source_uri` MANDATORY on every write
4. Identity (R06): `agent_id` MANDATORY on every write
5. Hygiene (R06): TTL + conflict detection in Phase 2
6. Recall: Keyword (Phase 1) → Semantic via Rust (Phase 2)
7. Single agent first (R05): Split only on proven divergence

## Scorecard (R01)
| Metric                     | Target   | Measurement          |
|----------------------------|----------|----------------------|
| Enrichment success rate    | ≥95%     | Monthly spot-audit   |
| Stale memory (past TTL)    | <5%      | Automated scan       |
| Correction propagation     | ≤2 min   | Fleet-wide sync      |
| Exception rate             | Tracked  | Per-agent weekly     |
| Source badge compliance    | 100%     | Gate check on write  |

## Owner (R02)
**[ASSIGN HUMAN OWNER HERE]**
Responsibilities: Scope ownership, output review, API key custody, blame acceptance.
Approves glossary terms and memory policy changes.
Serves as human gate for outward agent actions.

## Consequences
- ✅ source_uri mandatory → VAL_MISSING_SOURCE_BADGE if missing
- ✅ Enrichment cached → reduced cost, consistent results
- ✅ Content guarded → §17 compliance automatic
- ⚠️ File store = single-process → Rust migration in Phase 2
- ⚠️ Keyword recall limited → Semantic search deferred
- ❌ No direct LLM calls for memory — must use GovernedMemoryStore

## References
- Ten Rules for AI Agents (Caura): R01-R07
- Master Prompt: §3 Ownership, §4 Production Standard, §6 ErrorEnvelope
- OG Interaction Protocol: 5-Layer Defense
