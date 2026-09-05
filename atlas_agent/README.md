# Atlas AI — Code Generator Module

> **Status:** active | **Owner:** atlas_agent_team | **Language:** Python
> **Policy:** governance/policies/global-policy.yaml + governance/policies/security-policy.yaml
> **Contract:** contracts/schemas/ai/llm-invocation-v1.json

## Purpose

Orchestrate production-grade code generation through a governed pipeline:
**Governance Validation → SpecGen Scaffold → LLM Logic Fill → Human Gate → Archive**.

This module does NOT generate code directly via raw LLM prompts. It invokes LLM
providers through strict contracts that enforce privacy, security, and business
logic protection per CONSTITUTION.md §17.

## Boundary

### OWNS
- Code generation pipeline orchestration
- LLM provider abstraction (Groq, Claude, APInex)
- Internal learning memory (generation experiences only)
- Governance gate enforcement before LLM invocation
- Human approval workflow
- Anti-pattern registry (never repeat rejected patterns)

### DOES NOT OWN
- Trading agent memory (→ intelligence/memory_system/)
- Deterministic scaffold generation (→ tools/specgen/)
- Exchange connectivity (→ services/exchanges/)
- Market data processing (→ core_engine/market_data/)
- Risk engine logic (→ risk/risk_engine/)

### MUST NOT
- Send source code, strategies, or market data to external LLM providers
- Generate HFT core, execution logic, risk engines, or trading strategies via LLM
- Bypass governance validation before LLM invocation
- Store API keys in code or logs
- Operate without human approval gate for production artifacts
- Create parallel memory systems outside this module

## Architecture

    Human Request (Requirement + Language + Module)
            |
            v
    +---------------------------+
    | 1. GOVERNANCE GATE        | <-- Validate against policies + §17
    +----------+----------------+     FAIL → Reject, no LLM call
               | PASS
               v
    +---------------------------+
    | 2. SPECGEN SCAFFOLD       | <-- tools/specgen (deterministic)
    +----------+----------------+     No LLM at this stage
               |
               v
    +---------------------------+
    | 3. LEARNING MEMORY        | <-- Retrieve approved/rejected examples
    +----------+----------------+     Load anti-patterns to avoid
               |
               v
    +---------------------------+
    | 4. LLM INVOCATION         | <-- Contract-based, privacy-guarded
    +----------+----------------+     Provider: Groq → Claude → fallback
               |
               v
    +---------------------------+
    | 5. PRODUCTION GATES (x5)  | <-- Governance, no-float, error-handling
    +----------+----------------+     FAIL → Auto-reject + anti-pattern
               | ALL PASS
               v
    +---------------------------+
    | 6. HUMAN GATE             | <-- approve ✅ / reject ❌ / edit ✏️
    +----------+----------------+
               |
               v
        UPDATE Learning Memory

## Internal Learning Memory

SCOPE: Only code generation experiences (NOT trading agent memory).

| Stored ✅ | NOT Stored ❌ |
|-----------|---------------|
| Generation metadata | Full source code sent to LLM |
| Human decision + reason | API keys or credentials |
| Anti-patterns extracted | Raw LLM responses |
| Governance refs used | Market data or strategies |

File: atlas_agent/memory/portable_memory.jsonl (<50MB, portable)

## LLM Provider Contract

Invocation governed by: contracts/schemas/ai/llm-invocation-v1.json

| Provider | Status | Notes |
|----------|--------|-------|
| Groq | 🟡 Under Evaluation | Testing reliability + quality |
| Claude | ⚪ Planned | Pending API access |
| APInex | ⚪ Planned | Multi-model proxy |

Privacy: VPS (trusted) → sanitize → External LLM (untrusted)

## Resource Budget (6GB RAM / 6 CPU VPS)

| Component | RAM | CPU | HDD |
|-----------|-----|-----|-----|
| Learning Memory | <20 MB | negligible | <50 MB |
| LLM Client | <20 MB | I/O bound | 0 |
| Python Runtime | <50 MB | baseline | 0 |
| **Total** | **<100 MB** | **<0.5 core** | **<50 MB** |

## Governance Alignment

| Policy | Compliance |
|--------|------------|
| global-policy.yaml | ✅ governance.py |
| security-policy.yaml | ✅ privacy_guard.py |
| CONSTITUTION.md §17 | ✅ contract.py |
| ARCHITECTURE_LOCK.md | ✅ No parallel paths |
