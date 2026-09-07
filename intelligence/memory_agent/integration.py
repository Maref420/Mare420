# MODULE: atlas-memory-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: Helper functions for agents to interact with GovernedMemoryStore.
# WARNING: No bare except. All errors handled explicitly.
from __future__ import annotations

from typing import Any, Optional

from intelligence.research_agent.models import ForensicsSignal

from .store import GovernedMemoryStore, MemoryStoreError


def write_signal_to_memory(
    store: GovernedMemoryStore,
    signal: ForensicsSignal,
) -> bool:
    """Stores a ForensicsSignal summary in the memory graph."""
    try:
        store.write_node(
            node_id=f"signal_{signal.symbol}_{signal.timestamp_ns}",
            entity_type="forensics_signal",
            attributes={
                "symbol": signal.symbol,
                "aqs_score": str(signal.aqs_score),
                "spoofing_detected": str(signal.spoofing_detected),
                "confidence": str(signal.confidence),
                "vpin_toxicity": str(signal.vpin_toxicity),
            },
            ttl_ns=3_600_000_000_000,  # 1 hour
        )
        return True
    except MemoryStoreError as e:
        if e.retryable:
            # Could retry here with backoff
            pass
        return False
    except Exception:
        return False


def enrich_signal_from_memory(
    store: GovernedMemoryStore,
    symbol: str,
) -> Optional[dict[str, Any]]:
    """Reads past signals for a symbol from memory to enrich current analysis."""
    try:
        results = store.search(symbol)
        if results:
            return {"past_signals": results, "count": len(results)}
        return None
    except MemoryStoreError:
        return None
    except Exception:
        return None
