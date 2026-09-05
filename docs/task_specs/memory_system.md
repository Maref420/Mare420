# Memory System — Task Specification

## Identity

- Module: intelligence/memory_system/
- Language: Python
- Owner: intelligence_team
- Policy: governance/policies/python-policy.yaml

## Responsibility

Store strategy signals and outcomes for future learning. ONLY after outcome is known
(not at signal receipt time). Link signal -> outcome -> lesson.

## Input Contract

Experience Event containing: original StrategySignalEventV1 JSON + execution outcome +
risk assessment result. Entry point: experience_engine/subscriber.py.

## Processing Rules

1. Signal-only storage forbidden (must have outcome)
2. Episodic Memory: signal + outcome as episode
3. Procedural Memory: pattern extraction from successful/failed signals
4. Semantic Memory: regime/symbol/confidence correlations
5. Forgetting: decay based on recency + relevance
6. Consolidation: periodic batch processing

## Output / Side Effects

- Memory records in storage backend
- Retrieval index updates
- Consolidation summaries

## Failure Behavior

- Storage Error: retry 3x, then drop (never block pipeline)
- Invalid Experience: skip + audit log
- Consolidation Failure: log + retry next cycle

## Forbidden Actions

- Store signal without outcome
- Modify original signal payload
- Real-time processing in signal path (async only)
- Unbounded memory growth
- Expose raw memory to external systems without retrieval engine

## Dependencies

- <- core_engine/execution (Outcome Event)
- <- risk/risk_engine (Assessment)
- <- core_engine/strategy (Original Signal)
- -> Storage Backend
- -> Retrieval Engine

## Acceptance Criteria

- Signal + Outcome -> stored as episode
- Signal without outcome -> rejected
- Memory growth bounded by policy
- Retrieval returns relevant past experiences
- Forgetting respects decay parameters
