# Memory System

> **Status:** infrastructure_ready | **Owner:** intelligence_team | **Language:** Python
> **Contract:** contracts/schemas/memory/memory-experience-event-v1.json | **Policy:** governance/policies/python-policy.yaml
> **Architecture Review:** ARCH-REVIEW-002

## Purpose

Store strategy signals paired with execution outcomes for future learning.
Signals are ONLY stored AFTER outcome is known. Never store signal-only records.
This enables episodic, procedural, and semantic learning from trading experience.

## Architecture

    Execution Outcome Event (from Go Broker)
            |
            v
    +-------------------------+
    | Subscriber              | <-- Receive events from broker
    | (experience_engine/     |     Governed by memory-experience-event-v1.json
    |  subscriber.py)         |
    +------------+------------+
                 |
                 v
    +-------------------------+
    | Experience Engine       | <-- Link signal + outcome
    | (experience_engine/     |     Validate completeness
    |  engine.py)             |
    +------------+------------+
                 |
        +--------+--------+
        |        |        |
        v        v        v
    Episodic  Procedural  Semantic
    Memory    Memory      Memory
    (store)   (store)     (store)
        |        |        |
        +--------+--------+
                 |
                 v
    +-------------------------+
    | Consolidation Engine    | <-- Periodic batch processing
    | (consolidation/engine)  |
    +-------------------------+
                 |
                 v
    +-------------------------+
    | Forgetting Engine       | <-- Decay by recency + relevance
    | (forgetting/engine)     |
    +-------------------------+

## Subsystems

| Subsystem | Path | Purpose |
|-----------|------|---------|
| Subscriber | experience_engine/subscriber.py | Receive events from broker |
| Experience Engine | experience_engine/engine.py | Link signal + outcome |
| Episodic Memory | episodic_memory/store.py | Raw episode storage |
| Procedural Memory | procedural_memory/store.py | Pattern extraction |
| Semantic Memory | semantic_memory/store.py | Correlation analysis |
| Working Memory | working_memory/store.py | Short-term buffer |
| Retrieval Engine | retrieval_engine/engine.py | Query interface |
| Consolidation | consolidation/engine.py | Batch summarization |
| Forgetting | forgetting/engine.py | Decay management |
| Memory Kernel | memory_kernel/kernel.py | Core abstractions |
| Validation | memory_validation/validator.py | Input validation |
| Storage | storage/interface.py | Backend abstraction |
| Models | models/memory_record.py | Data structures |

## Input Specification

Experience Event containing:
- Original StrategySignalEventV1 JSON
- Execution outcome (filled/rejected/cancelled/halted)
- Risk assessment result (pass/warn/block)

Entry point: experience_engine/subscriber.py

## Processing Rules

1. Signal-only storage FORBIDDEN (must have outcome)
2. Episodic: store signal + outcome as immutable episode
3. Procedural: extract patterns from successful/failed signals
4. Semantic: correlate regime/symbol/confidence with outcomes
5. Forgetting: decay based on recency + relevance scores
6. Consolidation: periodic batch processing (not real-time)

## Integration Guide

### Subscribing to Execution Outcomes

    # subscriber.py already handles broker event reception
    # To add strategy signal linking:

    from intelligence.memory_system.experience_engine.engine import ExperienceEngine

    engine = ExperienceEngine()
    engine.store_experience(
        signal_event=original_strategy_signal_json,
        outcome=execution_outcome_dict,
        risk_assessment=risk_decision_dict,
    )

## Failure Behavior

- Storage Error: retry 3x, then drop (never block pipeline)
- Invalid Experience: skip + audit log
- Consolidation Failure: log + retry next cycle

## Governance

| Artifact | Location |
|----------|----------|
| Subscriber | intelligence/memory_system/experience_engine/subscriber.py |
| Experience Engine | intelligence/memory_system/experience_engine/engine.py |
| Contract | contracts/schemas/memory/memory-experience-event-v1.json |
| Arch Review | ARCH-REVIEW-002 |

### Forbidden Actions

- Store signal without outcome
- Modify original signal payload
- Real-time processing in signal path (async only)
- Unbounded memory growth
- Expose raw memory to external systems without retrieval engine

## Known Gaps

| Gap | Impact | Priority |
|-----|--------|----------|
| Strategy signal not linked to execution outcome | Learning loop incomplete | P2 |
| Subscriber not connected to strategy.signal.v1 topic | Events not received | P2 |
| Forgetting parameters not calibrated | Memory may grow unbounded | P3 |
| Retrieval engine not tested with strategy data | Recall quality unknown | P3 |
