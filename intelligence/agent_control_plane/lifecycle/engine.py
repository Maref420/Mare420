from typing import ClassVar

from intelligence.agent_control_plane.identity.models import (
    AgentIdentity,
    AgentStatus,
)
from intelligence.agent_control_plane.registry.registry import AgentRegistry


class AgentLifecycleEngine:
    """Controlled Agent lifecycle state machine."""

    _TRANSITIONS: ClassVar[
        dict[AgentStatus, frozenset[AgentStatus]]
    ] = {
        AgentStatus.CREATED: frozenset({AgentStatus.VALIDATED}),
        AgentStatus.VALIDATED: frozenset({AgentStatus.READY}),
        AgentStatus.READY: frozenset(
            {AgentStatus.RUNNING, AgentStatus.TERMINATED}
        ),
        AgentStatus.RUNNING: frozenset(
            {AgentStatus.SUSPENDED, AgentStatus.TERMINATED}
        ),
        AgentStatus.SUSPENDED: frozenset(
            {AgentStatus.READY, AgentStatus.TERMINATED}
        ),
        AgentStatus.TERMINATED: frozenset(),
    }

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def transition(
        self,
        agent_id: str,
        target_status: AgentStatus,
    ) -> AgentIdentity:
        identity = self._registry.get(agent_id)

        if identity is None:
            raise PermissionError("Unknown Agent.")

        allowed = self._TRANSITIONS[identity.status]

        if target_status not in allowed:
            raise ValueError(
                f"Invalid lifecycle transition: "
                f"{identity.status.value} -> {target_status.value}"
            )

        updated = identity.model_copy(update={"status": target_status})
        self._registry.replace(updated)
        return updated

    def startup(self, agent_id: str) -> AgentIdentity:
        identity = self._registry.get(agent_id)

        if identity is None:
            raise PermissionError("Unknown Agent.")

        if identity.status is AgentStatus.VALIDATED:
            self.transition(agent_id, AgentStatus.READY)

        identity = self._registry.get(agent_id)
        if identity is None:
            raise RuntimeError("Agent disappeared during startup.")

        if identity.status is AgentStatus.READY:
            return self.transition(agent_id, AgentStatus.RUNNING)

        raise ValueError(
            f"Agent cannot start from state: {identity.status.value}"
        )

    def suspend(self, agent_id: str) -> AgentIdentity:
        return self.transition(agent_id, AgentStatus.SUSPENDED)

    def resume(self, agent_id: str) -> AgentIdentity:
        return self.transition(agent_id, AgentStatus.READY)

    def shutdown(self, agent_id: str) -> AgentIdentity:
        identity = self._registry.get(agent_id)

        if identity is None:
            raise PermissionError("Unknown Agent.")

        if identity.status not in {
            AgentStatus.READY,
            AgentStatus.RUNNING,
            AgentStatus.SUSPENDED,
        }:
            raise ValueError(
                f"Agent cannot shutdown from state: "
                f"{identity.status.value}"
            )

        return self.transition(agent_id, AgentStatus.TERMINATED)
