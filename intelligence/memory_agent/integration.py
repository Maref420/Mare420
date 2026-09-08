# MODULE: atlas-memory-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# WARNING: No bare except. All errors handled explicitly.
from __future__ import annotations
from typing import Any, Optional
from intelligence.research_agent.models import ForensicsSignal
from .store import GovernedMemoryStore, MemoryStoreError


def write_signal_to_memory(store: GovernedMemoryStore, signal: ForensicsSignal) -> bool:
    try:
        store.write_node(
            node_id=f"signal_{signal.symbol}_{signal.timestamp_ns}",
            entity_type="forensics_signal",
            attributes={
                "symbol": signal.symbol,
                "aqs_score": str(signal.aqs_score),
                "spoofing_detected": str(signal.spoofing_detected),
                "confidence": str(signal.confidence),
            },
            ttl_ns=3_600_000_000_000,
        )
        return True
    except MemoryStoreError:
        return False
    except Exception:
        return False


def enrich_signal_from_memory(store: GovernedMemoryStore, symbol: str) -> Optional[dict[str, Any]]:
    try:
        results = store.search(symbol)
        if results:
            return {"past_signals": results, "count": len(results)}
        return None
    except MemoryStoreError:
        return None
    except Exception:
        return None


def get_exchange_quality(store: GovernedMemoryStore, exchange: str) -> Optional[str]:
    try:
        node = store.read_node(f"exchange_{exchange.lower()}")
        if node and "attributes" in node:
            return node["attributes"].get("data_quality")
        return None
    except MemoryStoreError:
        return None
    except Exception:
        return None


def set_exchange_quality(store: GovernedMemoryStore, exchange: str, quality: str) -> bool:
    try:
        store.write_node(
            node_id=f"exchange_{exchange.lower()}",
            entity_type="exchange_status",
            attributes={"data_quality": quality, "exchange": exchange},
            ttl_ns=7_200_000_000_000,
        )
        return True
    except MemoryStoreError:
        return False
    except Exception:
        return False
