
# ADR-001: Execution Contract Version Resolution
## Status: APPROVED
## Date: 2026-08-30
## Decided By: Project Architect
## Decision: Option 2 — Two Distinct Layers
- Layer 1 (Python): Agent Task Execution v0.1 — orchestration scope
- Layer 2 (Rust): Exchange Order Execution v1.0 — trading scope
- Boundary: Agent Runtime produces trade intents, Execution Engine fulfills them
## Compliance: No parallel paths, no module ownership violation
