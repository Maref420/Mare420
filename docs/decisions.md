
# ADR-001: Execution Contract Version Resolution
## Status: APPROVED
## Date: 2026-08-30
## Decided By: Project Architect
## Decision: Option 2 — Two Distinct Layers
- Layer 1 (Python): Agent Task Execution v0.1 — orchestration scope
- Layer 2 (Rust): Exchange Order Execution v1.0 — trading scope
- Boundary: Agent Runtime produces trade intents, Execution Engine fulfills them
## Compliance: No parallel paths, no module ownership violation

---

# ADR-002: Cross-Language Memory Experience Event Pipeline

## Status: APPROVED

## Date: 2026-08-30

## Decided By: Project Architect

## Context

Memory System had complete CRUD infrastructure but no operational data
ingestion path from production systems. ExperienceEngine was empty.
No cross-language flow existed for memory events.

## Decision

Add a Cross-Language Memory Event Pipeline:
Rust Core → Go Broker → Python ExperienceEngine → Supabase

Key design decisions:
1. Go Broker as mandatory intermediary (complies with Dependency Rules)
2. Shared contract schema as single source of truth
3. Triple-layer validation (Rust + Go + Python)
4. HTTP polling transport initially, NATS as approved future upgrade
5. Fire-and-forget from Rust (never blocks order processing)

## Files Created/Modified

New:
- contracts/schemas/memory/memory-experience-event-v1.json
- core_engine/execution/src/memory_events.rs
- intelligence/memory_system/experience_engine/engine.py
- intelligence/memory_system/experience_engine/subscriber.py
- services/message_broker/cmd/validate/main.go
- tests/production/test_cross_language_memory_pipeline.py
- tests/memory_system/test_experience_engine_production.py

Modified:
- core_engine/execution/src/lib.rs
- core_engine/execution/src/gateway.rs
- services/message_broker/internal/envelope/envelope.go

## Compliance

- No parallel paths created
- No module ownership violation
- Dependency Rules respected (Rust→Infrastructure→Python)
- Architecture Review ARCH-REVIEW-002 completed
- 28 production tests passing across all three languages
