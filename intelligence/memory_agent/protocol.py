# MODULE: atlas-memory-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: Inter-agent communication protocol via MemoryGraph.
# WARNING: No bare except. All errors handled explicitly.
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SignalPriority(Enum):
    """Agent processing order. Lower = processed first."""
    RESEARCH = 10
    DATA_QUALITY = 15
    ANALYST = 20
    PRICING = 30
    RISK = 40
    EXECUTION = 50


class SignalStatus(Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class SignalNode:
    """Standardized signal written by any agent to MemoryGraph."""
    signal_id: str
    agent_id: str
    entity_type: str
    symbol: str
    direction: str          # BUY, SELL, HOLD, ALERT
    confidence: float       # 0.0 to 1.0
    attributes: dict[str, str]
    source_uri: str
    priority: SignalPriority
    ttl_ns: int = 3_600_000_000_000  # 1 hour default
    status: SignalStatus = SignalStatus.PENDING
    created_at_ns: int = 0
    parent_signal_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.created_at_ns == 0:
            self.created_at_ns = int(time.time() * 1e9)
        if not self.signal_id:
            self.signal_id = f"{self.agent_id}_{self.symbol}_{self.created_at_ns}"

    def to_node_dict(self) -> dict[str, Any]:
        """Convert to MemoryGraph-compatible node payload."""
        attrs = {**self.attributes}
        attrs.update({
            "direction": self.direction,
            "confidence": str(self.confidence),
            "priority": str(self.priority.value),
            "status": self.status.value,
            "symbol": self.symbol,
            "parent_signals": ",".join(self.parent_signal_ids),
        })
        return {
            "node_id": self.signal_id,
            "entity_type": self.entity_type,
            "attributes": attrs,
            "source_uri": self.source_uri,
            "agent_id": self.agent_id,
            "ttl_ns": self.ttl_ns,
            "created_at_ns": self.created_at_ns,
            "updated_at_ns": self.created_at_ns,
        }

    @classmethod
    def from_node_dict(cls, data: dict[str, Any]) -> SignalNode | None:
        """Reconstruct SignalNode from MemoryGraph node data."""
        try:
            attrs = dict(data.get("attributes", {}))
            direction = attrs.pop("direction", "HOLD")
            confidence = float(attrs.pop("confidence", "0.0"))
            priority_val = int(attrs.pop("priority", "20"))
            status_str = attrs.pop("status", "pending")
            symbol = attrs.pop("symbol", "")
            parents_str = attrs.pop("parent_signals", "")
            parents = [p for p in parents_str.split(",") if p]

            priority = SignalPriority(priority_val)
            status = SignalStatus(status_str)

            return cls(
                signal_id=data["node_id"],
                agent_id=data["agent_id"],
                entity_type=data["entity_type"],
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                attributes=attrs,
                source_uri=data["source_uri"],
                priority=priority,
                ttl_ns=data.get("ttl_ns", 0),
                status=status,
                created_at_ns=data.get("created_at_ns", 0),
                parent_signal_ids=parents,
            )
        except (KeyError, ValueError, TypeError):
            return None


@dataclass
class AgentMessage:
    """Direct message between agents stored in MemoryGraph."""
    message_id: str
    from_agent: str
    to_agent: str
    message_type: str       # REQUEST, RESPONSE, ALERT, LESSON
    payload: dict[str, Any]
    source_uri: str
    created_at_ns: int = 0
    ttl_ns: int = 86_400_000_000_000  # 24 hours

    def __post_init__(self) -> None:
        if self.created_at_ns == 0:
            self.created_at_ns = int(time.time() * 1e9)
        if not self.message_id:
            self.message_id = f"msg_{self.from_agent}_{self.created_at_ns}"

    def to_node_dict(self) -> dict[str, Any]:
        attrs = {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type,
            "payload": str(self.payload),
        }
        return {
            "node_id": self.message_id,
            "entity_type": "agent_message",
            "attributes": attrs,
            "source_uri": self.source_uri,
            "agent_id": self.from_agent,
            "ttl_ns": self.ttl_ns,
            "created_at_ns": self.created_at_ns,
            "updated_at_ns": self.created_at_ns,
        }
