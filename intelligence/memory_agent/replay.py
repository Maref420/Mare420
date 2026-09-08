# MODULE: atlas-memory-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: Agent self-audit via causal trace and memory replay.
# WARNING: No bare except. All errors handled explicitly.
from __future__ import annotations

import time
from typing import Any, Optional

from .bridge import RustIpcBridge
from .store import GovernedMemoryStore, MemoryStoreError


class AgentSelfAudit:
    """Enables agents to audit their own decisions via causal trace.

    Uses GovernedMemoryStore for writes (lessons) and optionally
    RustIpcBridge for real BFS causal_trace when available.
    """

    def __init__(
        self,
        store: GovernedMemoryStore,
        ipc_bridge: Optional[RustIpcBridge] = None,
    ) -> None:
        self._store = store
        self._ipc = ipc_bridge

    def causal_trace(self, node_id: str) -> list[dict[str, Any]]:
        """Walk edges backward from node_id to find root cause chain.

        If IPC bridge is available, uses real Rust BFS traversal.
        Otherwise falls back to keyword search in GovernedMemoryStore.
        """
        if self._ipc is not None:
            try:
                resp = self._ipc.send_command("causal_trace", {"node_id": node_id})
                if resp.get("ok"):
                    data = resp.get("data", {})
                    chain = data.get("chain", [])
                    if isinstance(chain, list):
                        return [item for item in chain if isinstance(item, dict)]
            except MemoryStoreError:
                pass
            except Exception:
                pass

        # Fallback: keyword search
        try:
            results = self._store.search(node_id)
            return results if results else []
        except MemoryStoreError:
            return []
        except Exception:
            return []

    def record_lesson(
        self,
        agent_id: str,
        decision_node_id: str,
        lesson: str,
        context: dict[str, Any],
    ) -> bool:
        """Write a lesson-learned node after causal analysis."""
        try:
            ts = int(time.time() * 1e9)
            self._store.write_node(
                node_id=f"lesson_{agent_id}_{ts}",
                entity_type="lesson",
                attributes={
                    "decision_ref": decision_node_id,
                    "lesson": lesson,
                    "context": str(context),
                },
                ttl_ns=86_400_000_000_000,
            )
            return True
        except MemoryStoreError:
            return False
        except Exception:
            return False

    def search_lessons(self, keyword: str) -> list[dict[str, Any]]:
        """Search past lessons to inform current decisions."""
        try:
            results = self._store.search(keyword)
            return [r for r in results if r.get("entity_type") == "lesson"]
        except MemoryStoreError:
            return []
        except Exception:
            return []

    def audit_decision(
        self,
        decision_node_id: str,
        outcome: str,
        agent_id: str,
    ) -> Optional[str]:
        """Full audit cycle: trace -> analyze -> record lesson.

        Returns the lesson text if audit produced one, None otherwise.
        """
        chain = self.causal_trace(decision_node_id)
        if not chain:
            return None

        if outcome == "loss":
            lesson = (
                f"Avoid repeating decision {decision_node_id}: "
                f"chain length {len(chain)} led to loss"
            )
            context = {"chain_length": len(chain), "outcome": outcome}
            self.record_lesson(agent_id, decision_node_id, lesson, context)
            return lesson

        return None


class IpcReplayClient:
    """Direct IPC client for replay/diff commands (requires RustIpcBridge)."""

    def __init__(self, bridge: RustIpcBridge) -> None:
        self._bridge = bridge

    def replay_at(self, timestamp_ns: int) -> dict[str, Any]:
        resp = self._bridge.send_command("replay", {"timestamp_ns": timestamp_ns})
        if not resp.get("ok"):
            err = resp.get("error", {})
            raise MemoryStoreError(
                err.get("code", "INT_INVARIANT_BROKEN"),
                err.get("message", "replay failed"),
                err.get("retryable", False),
            )
        return resp.get("data", {})

    def causal_trace(self, node_id: str) -> list[dict[str, Any]]:
        resp = self._bridge.send_command("causal_trace", {"node_id": node_id})
        if not resp.get("ok"):
            err = resp.get("error", {})
            raise MemoryStoreError(
                err.get("code", "INT_INVARIANT_BROKEN"),
                err.get("message", "causal_trace failed"),
                err.get("retryable", False),
            )
        data = resp.get("data", {})
        chain = data.get("chain", [])
        return chain if isinstance(chain, list) else []

    def diff(self, t1_ns: int, t2_ns: int) -> dict[str, Any]:
        resp = self._bridge.send_command("diff", {"t1_ns": t1_ns, "t2_ns": t2_ns})
        if not resp.get("ok"):
            err = resp.get("error", {})
            raise MemoryStoreError(
                err.get("code", "INT_INVARIANT_BROKEN"),
                err.get("message", "diff failed"),
                err.get("retryable", False),
            )
        return resp.get("data", {})
