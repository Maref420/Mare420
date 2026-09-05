"""Shared fixtures for production-grade cross-language tests."""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(scope="session")
def canonical_strategy_signal_json() -> str:
    """Load the canonical strategy signal event fixture."""
    path = FIXTURES_DIR / "strategy" / "strategy-signal-event-v1-canonical.json"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def canonical_strategy_signal_dict(canonical_strategy_signal_json: str) -> dict:
    """Parsed canonical fixture as dict."""
    return json.loads(canonical_strategy_signal_json)
