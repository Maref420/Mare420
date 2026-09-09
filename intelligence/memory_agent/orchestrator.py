# MODULE: atlas-memory-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: Agent orchestration via MemoryGraph.
# Coordinates signal flow between agents using shared memory.
# WARNING: No bare except. All errors handled explicitly.
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from .protocol import (
    AgentMessage,
    SignalNode,
    SignalPriority,
    SignalStatus,
)
from .store import GovernedMemoryStore, MemoryStoreError


class MemoryGraphAgent:
    """Orchestrates agent signal flow through MemoryGraph.

    Responsibilities:
    1. Publish signals from agents into shared memory
    2. Deduplicate similar signals within time window
    3. Route signals to downstream agents by priority
    4. Track signal lifecycle (pending -> processed -> expired)
    5. Enable agents to query upstream signals before deciding
    """

    def __init__(
        self,
        store: GovernedMemoryStore,
        agent_id: str,
        dedup_window_ns: int = 300_000_000_000,  # 5 minutes
    ) -> None:
        self._store = store
        self._agent_id = agent_id
        self._dedup_window_ns = dedup_window_ns
        self._handlers: dict[str, Callable[[SignalNode], Optional[SignalNode]]] = {}

    def register_handler(
        self,
        entity_type: str,
        handler: Callable[[SignalNode], Optional[SignalNode]],
    ) -> None:
        """Register a handler function for a specific signal type."""
        self._handlers[entity_type] = handler

    def publish_signal(self, signal: SignalNode) -> bool:
        """Publish a signal to MemoryGraph with deduplication check."""
        if self._is_duplicate(signal):
            return False

        try:
            node_data = signal.to_node_dict()
            # Store original agent_id in attributes so search can find it
            node_data["attributes"]["original_agent_id"] = signal.agent_id
            self._store.write_node(
                node_id=node_data["node_id"],
                entity_type=node_data["entity_type"],
                attributes=node_data["attributes"],
                ttl_ns=node_data["ttl_ns"],
            )
            return True
        except MemoryStoreError:
            return False
        except Exception:
            return False

    def _is_duplicate(self, signal: SignalNode) -> bool:
        """Check if a similar signal was published within dedup window."""
        try:
            now_ns = int(time.time() * 1e9)
            cutoff_ns = now_ns - self._dedup_window_ns
            existing = self._store.search(signal.symbol)
            for node in existing:
                if node.get("entity_type") != signal.entity_type:
                    continue
                attrs = node.get("attributes", {})
                # Check original_agent_id stored in attributes
                node_agent = attrs.get("original_agent_id", node.get("agent_id", ""))
                if node_agent != signal.agent_id:
                    continue
                if attrs.get("direction") == signal.direction:
                    created = node.get("created_at_ns", 0)
                    if created >= cutoff_ns:
                        return True
            return False
        except MemoryStoreError:
            return False
        except Exception:
            return False

    def get_upstream_signals(
        self,
        symbol: str,
        max_priority: SignalPriority,
    ) -> list[SignalNode]:
        """Get signals from upstream agents (lower priority number)."""
        try:
            results = self._store.search(symbol)
            signals: list[SignalNode] = []
            for node in results:
                sig = SignalNode.from_node_dict(node)
                if sig is None:
                    continue
                # Restore original agent_id from attributes
                attrs = node.get("attributes", {})
                original_agent = attrs.get("original_agent_id", "")
                if original_agent:
                    sig.agent_id = original_agent
                if sig.priority.value > max_priority.value:
                    continue
                if sig.status == SignalStatus.EXPIRED:
                    continue
                signals.append(sig)
            signals.sort(key=lambda s: s.priority.value)
            return signals
        except MemoryStoreError:
            return []
        except Exception:
            return []

    def process_pending_signals(
        self,
        entity_type: str,
    ) -> list[SignalNode]:
        """Process pending signals of a given type through registered handler."""
        handler = self._handlers.get(entity_type)
        if handler is None:
            return []

        try:
            results = self._store.search(entity_type)
            processed: list[SignalNode] = []
            for node in results:
                sig = SignalNode.from_node_dict(node)
                if sig is None:
                    continue
                if sig.status != SignalStatus.PENDING:
                    continue
                try:
                    result = handler(sig)
                    if result is not None:
                        result.status = SignalStatus.PROCESSED
                        self.publish_signal(result)
                        processed.append(result)
                except MemoryStoreError:
                    continue
                except Exception:
                    continue
            return processed
        except MemoryStoreError:
            return []
        except Exception:
            return []

    def send_message(
        self,
        to_agent: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> bool:
        """Send a direct message to another agent via MemoryGraph."""
        try:
            msg = AgentMessage(
                message_id="",
                from_agent=self._agent_id,
                to_agent=to_agent,
                message_type=message_type,
                payload=payload,
                source_uri=f"agent://{self._agent_id}/message",
            )
            node_data = msg.to_node_dict()
            self._store.write_node(
                node_id=node_data["node_id"],
                entity_type="agent_message",
                attributes=node_data["attributes"],
                ttl_ns=node_data["ttl_ns"],
            )
            return True
        except MemoryStoreError:
            return False
        except Exception:
            return False

    def get_messages(
        self,
        message_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Retrieve messages addressed to this agent."""
        try:
            results = self._store.search("agent_message")
            messages: list[dict[str, Any]] = []
            for node in results:
                attrs = node.get("attributes", {})
                if attrs.get("to_agent") != self._agent_id:
                    continue
                if message_type and attrs.get("message_type") != message_type:
                    continue
                messages.append(node)
            return messages
        except MemoryStoreError:
            return []
        except Exception:
            return []

    def get_signal_chain(
        self,
        symbol: str,
    ) -> list[SignalNode]:
        """Get full signal chain for a symbol, ordered by priority."""
        try:
            results = self._store.search(symbol)
            signals: list[SignalNode] = []
            for node in results:
                sig = SignalNode.from_node_dict(node)
                if sig is not None:
                    attrs = node.get("attributes", {})
                    original_agent = attrs.get("original_agent_id", "")
                    if original_agent:
                        sig.agent_id = original_agent
                    signals.append(sig)
            signals.sort(key=lambda s: s.priority.value)
            return signals
        except MemoryStoreError:
            return []
        except Exception:
            return []
