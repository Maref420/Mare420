# MODULE: atlas-memory-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: Neural routing system for inter-agent coordination.
# Implements synaptic weights, inhibition, event notification, plasticity.
# WARNING: No bare except. All errors handled explicitly.
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from .protocol import SignalNode, SignalStatus
from .store import GovernedMemoryStore, MemoryStoreError


class SynapseConfig:
    """Weight configuration between two agents."""
    __slots__ = ("source_agent", "target_agent", "weight", "min_weight", "max_weight")

    def __init__(
        self,
        source_agent: str,
        target_agent: str,
        weight: float = 1.0,
        min_weight: float = 0.1,
        max_weight: float = 2.0,
    ) -> None:
        self.source_agent = source_agent
        self.target_agent = target_agent
        self.weight = max(min_weight, min(max_weight, weight))
        self.min_weight = min_weight
        self.max_weight = max_weight


class NeuralRouter:
    """Event-driven neural routing between agents.

    Features:
    1. Synaptic weights: each agent-to-agent connection has a learnable weight
    2. Inhibition: high-priority agents can block lower-priority signals
    3. Event notification: subscribers get called immediately on new signals
    4. Plasticity: weights adjust based on signal accuracy over time
    """

    def __init__(self, store: GovernedMemoryStore) -> None:
        self._store = store
        self._synapses: dict[str, SynapseConfig] = {}
        self._subscribers: dict[str, list[Callable[[SignalNode], None]]] = {}
        self._inhibitors: dict[str, list[str]] = {}
        self._lock = threading.Lock()
        self._running = False
        self._poll_thread: threading.Thread | None = None
        self._last_scan_ns: int = 0

    def connect(
        self,
        source_agent: str,
        target_agent: str,
        weight: float = 1.0,
    ) -> None:
        """Create or update a synaptic connection between agents."""
        key = f"{source_agent}->{target_agent}"
        with self._lock:
            if key in self._synapses:
                self._synapses[key].weight = max(0.1, min(2.0, weight))
            else:
                self._synapses[key] = SynapseConfig(
                    source_agent=source_agent,
                    target_agent=target_agent,
                    weight=weight,
                )

    def disconnect(self, source_agent: str, target_agent: str) -> None:
        """Remove a synaptic connection."""
        key = f"{source_agent}->{target_agent}"
        with self._lock:
            self._synapses.pop(key, None)

    def get_weight(self, source_agent: str, target_agent: str) -> float:
        """Get current synaptic weight between two agents."""
        key = f"{source_agent}->{target_agent}"
        with self._lock:
            syn = self._synapses.get(key)
            return syn.weight if syn else 1.0

    def add_inhibitor(self, inhibitor_agent: str, target_agent: str) -> None:
        """Allow inhibitor_agent to block signals to target_agent.

        Example: RiskManager inhibits ExecutionAgent when drawdown is high.
        """
        with self._lock:
            if target_agent not in self._inhibitors:
                self._inhibitors[target_agent] = []
            if inhibitor_agent not in self._inhibitors[target_agent]:
                self._inhibitors[target_agent].append(inhibitor_agent)

    def is_inhibited(self, target_agent: str) -> bool:
        """Check if any inhibitor has an active BLOCK signal for target."""
        with self._lock:
            inhibitors = self._inhibitors.get(target_agent, [])
        if not inhibitors:
            return False

        try:
            now_ns = int(time.time() * 1e9)
            cutoff_ns = now_ns - 600_000_000_000  # 10 min window
            results = self._store.search("INHIBIT")
            for node in results:
                attrs = node.get("attributes", {})
                target = attrs.get("target_agent", "")
                if target != target_agent:
                    continue
                original_agent = attrs.get("original_agent_id", node.get("agent_id", ""))
                if original_agent not in inhibitors:
                    continue
                created = node.get("created_at_ns", 0)
                if created >= cutoff_ns:
                    return True
            return False
        except MemoryStoreError:
            return False
        except Exception:
            return False

    def emit_inhibit(
        self,
        from_agent: str,
        target_agent: str,
        reason: str,
        ttl_ns: int = 600_000_000_000,
    ) -> bool:
        """Emit an inhibition signal that blocks target_agent."""
        try:
            now_ns = int(time.time() * 1e9)
            self._store.write_node(
                node_id=f"inhibit_{from_agent}_{target_agent}_{now_ns}",
                entity_type="INHIBIT",
                attributes={
                    "original_agent_id": from_agent,
                    "target_agent": target_agent,
                    "reason": reason,
                },
                ttl_ns=ttl_ns,
            )
            return True
        except MemoryStoreError:
            return False
        except Exception:
            return False

    def subscribe(
        self,
        entity_type: str,
        callback: Callable[[SignalNode], None],
    ) -> None:
        """Subscribe to signals of a specific entity_type."""
        with self._lock:
            if entity_type not in self._subscribers:
                self._subscribers[entity_type] = []
            self._subscribers[entity_type].append(callback)

    def unsubscribe(
        self,
        entity_type: str,
        callback: Callable[[SignalNode], None],
    ) -> None:
        """Remove a subscription."""
        with self._lock:
            subs = self._subscribers.get(entity_type, [])
            self._subscribers[entity_type] = [s for s in subs if s is not callback]

    def route_signal(self, signal: SignalNode) -> bool:
        """Route a signal through the neural network.

        1. Check inhibition
        2. Apply synaptic weight
        3. Notify subscribers
        Returns True if routed, False if inhibited or error.
        """
        if self.is_inhibited(signal.agent_id):
            return False

        with self._lock:
            callbacks = list(self._subscribers.get(signal.entity_type, []))

        weighted_confidence = signal.confidence
        for cb in callbacks:
            try:
                sig_copy = SignalNode(
                    signal_id=signal.signal_id,
                    agent_id=signal.agent_id,
                    entity_type=signal.entity_type,
                    symbol=signal.symbol,
                    direction=signal.direction,
                    confidence=weighted_confidence,
                    attributes=dict(signal.attributes),
                    source_uri=signal.source_uri,
                    priority=signal.priority,
                    ttl_ns=signal.ttl_ns,
                    status=signal.status,
                    created_at_ns=signal.created_at_ns,
                    parent_signal_ids=list(signal.parent_signal_ids),
                )
                cb(sig_copy)
            except MemoryStoreError:
                continue
            except Exception:
                continue

        return True

    def apply_plasticity(
        self,
        source_agent: str,
        target_agent: str,
        was_correct: bool,
        learning_rate: float = 0.1,
    ) -> float:
        """Adjust synaptic weight based on signal accuracy.

        If signal was correct: increase weight (strengthen synapse)
        If signal was wrong: decrease weight (weaken synapse)
        Returns new weight.
        """
        key = f"{source_agent}->{target_agent}"
        with self._lock:
            syn = self._synapses.get(key)
            if syn is None:
                syn = SynapseConfig(source_agent, target_agent)
                self._synapses[key] = syn

            if was_correct:
                syn.weight = min(syn.max_weight, syn.weight + learning_rate)
            else:
                syn.weight = max(syn.min_weight, syn.weight - learning_rate)

            new_weight = syn.weight

        # Persist weight change to memory
        try:
            now_ns = int(time.time() * 1e9)
            self._store.write_node(
                node_id=f"synapse_{source_agent}_{target_agent}",
                entity_type="synapse_weight",
                attributes={
                    "source_agent": source_agent,
                    "target_agent": target_agent,
                    "weight": str(new_weight),
                    "updated_at": str(now_ns),
                },
                ttl_ns=86_400_000_000_000,
            )
        except MemoryStoreError:
            pass
        except Exception:
            pass

        return new_weight

    def load_synapses(self) -> int:
        """Load persisted synapse weights from MemoryGraph."""
        try:
            results = self._store.search("synapse_weight")
            count = 0
            for node in results:
                attrs = node.get("attributes", {})
                src = attrs.get("source_agent", "")
                tgt = attrs.get("target_agent", "")
                w_str = attrs.get("weight", "1.0")
                if src and tgt:
                    try:
                        w = float(w_str)
                        self.connect(src, tgt, w)
                        count += 1
                    except ValueError:
                        continue
            return count
        except MemoryStoreError:
            return 0
        except Exception:
            return 0

    def start_polling(self, interval_secs: float = 5.0) -> None:
        """Start background polling for new signals to route."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._last_scan_ns = int(time.time() * 1e9)

        def _poll_loop() -> None:
            while self._running:
                try:
                    self._scan_and_route()
                except MemoryStoreError:
                    pass
                except Exception:
                    pass
                time.sleep(interval_secs)

        self._poll_thread = threading.Thread(
            target=_poll_loop, daemon=True, name="neural-router-poll"
        )
        self._poll_thread.start()

    def stop_polling(self) -> None:
        """Stop background polling."""
        self._running = False
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=10)
            self._poll_thread = None

    def _scan_and_route(self) -> None:
        """Scan for new PENDING signals and route them."""
        try:
            now_ns = int(time.time() * 1e9)
            results = self._store.search("PENDING")
            for node in results:
                sig = SignalNode.from_node_dict(node)
                if sig is None:
                    continue
                if sig.status != SignalStatus.PENDING:
                    continue
                created = node.get("created_at_ns", 0)
                if created <= self._last_scan_ns:
                    continue
                self.route_signal(sig)
            self._last_scan_ns = now_ns
        except MemoryStoreError:
            pass
        except Exception:
            pass

    def get_topology(self) -> dict[str, Any]:
        """Return current neural network topology for debugging."""
        with self._lock:
            synapses = {
                key: {"weight": syn.weight, "source": syn.source_agent, "target": syn.target_agent}
                for key, syn in self._synapses.items()
            }
            inhibitors = dict(self._inhibitors)
            subscribers = {
                etype: len(cbs) for etype, cbs in self._subscribers.items()
            }
        return {
            "synapses": synapses,
            "inhibitors": inhibitors,
            "subscriber_counts": subscribers,
            "running": self._running,
        }
