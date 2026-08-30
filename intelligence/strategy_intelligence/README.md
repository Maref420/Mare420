# Atlas AI Strategy Intelligence

Owner:
Intelligence Layer

Purpose:
Provide intelligent strategy selection and optimization based on market conditions.

Architecture Principle:
Strategy selection must be evidence-based, evaluated, and separated from execution.

Responsibilities:
- Analyze market regimes
- Classify strategy opportunities
- Select suitable strategies
- Calculate confidence
- Optimize parameters
- Evaluate strategy performance
- Maintain strategy memory
- Simulate strategies

Flow:

Market Intelligence
        |
        v
Market Regime
        |
        v
Strategy Selection
        |
        v
Confidence Evaluation
        |
        v
Risk Validation

Core Components:

Market Regime:
Identify current market conditions.

Strategy Registry:
Maintain strategy definitions.

Strategy Classifier:
Match market conditions with strategy types.

Strategy Selector:
Choose the most suitable strategy.

Confidence Engine:
Measure evidence quality.

Strategy Optimizer:
Improve parameters using validated data.

Strategy Evaluator:
Measure historical performance.

Strategy Memory:
Store strategy experiences.

Simulation Engine:
Validate before production use.

Forbidden:
- Direct order execution
- Risk bypass
- Exchange communication

Dependencies:
- Market Intelligence
- Agent Evaluation
- Memory System
- Risk Layer

Version:
v0.1

## Contract Binding
This module produces `strategy-signal-event-v1` events.
- Schema: `contracts/schemas/strategy/strategy-signal-event-v1.schema.json`
- Serializer: TBD (Phase 2)
- Validation: All outgoing events MUST pass schema validation before publish

## Contract Binding
This module produces `strategy-signal-event-v1` events.
- Schema: `contracts/schemas/strategy/strategy-signal-event-v1.schema.json`
- Serializer: TBD (Phase 2)
- Validation: All outgoing events MUST pass schema validation before publish

## Contract Binding
This module produces `strategy-signal-event-v1` events.
- Schema: `contracts/schemas/strategy/strategy-signal-event-v1.schema.json`
- Serializer: TBD (Phase 2)
- Validation: All outgoing events MUST pass schema validation before publish

## Contract Adapter (Phase 3)

Stdlib-only Python adapter for `strategy-signal-event-v1`.

- **File:** `intelligence/strategy_intelligence/contract_adapter.py`
- **Dependencies:** None (stdlib only: json, dataclasses, uuid, re)
- **Tests:** `tests/contracts/test_strategy_signal_python_contract.py` (11/11)

### Usage

```python
from intelligence.strategy_intelligence.contract_adapter import (
    StrategySignalEventV1,
)

# Create new event
event = StrategySignalEventV1.create(
    source_agent="strategy_selector_v2",
    symbol="BTCUSDT",
    direction="LONG",
    confidence=0.87,
    regime="TRENDING",
)

# Serialize
json_str = event.to_json()

# Deserialize with validation
restored = StrategySignalEventV1.from_json(json_str)
```

### Cross-Language Parity

Python adapter and Rust `contract_types.rs` enforce identical rules:
- Same JSON Schema source of truth
- Same field names and types
- Same validation constraints
- Round-trip compatible serialization
