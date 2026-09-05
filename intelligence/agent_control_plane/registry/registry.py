from intelligence.agent_control_plane.identity.models import AgentIdentity


class AgentRegistry:
    """Controlled registry for validated Agent identities."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentIdentity] = {}

    def register(self, identity: AgentIdentity) -> None:
        if identity.status.value != "validated":
            raise ValueError("Only validated agents may be registered.")

        if identity.agent_id in self._agents:
            raise ValueError("Agent is already registered.")

        self._agents[identity.agent_id] = identity

    def get(self, agent_id: str) -> AgentIdentity | None:
        if not agent_id:
            raise ValueError("agent_id must not be empty.")

        return self._agents.get(agent_id)

    def contains(self, agent_id: str) -> bool:
        return self.get(agent_id) is not None

    def replace(self, identity: AgentIdentity) -> None:
        if identity.agent_id not in self._agents:
            raise ValueError("Agent is not registered.")

        if identity.status.value == "created":
            raise ValueError("Registered Agent cannot return to created state.")

        self._agents[identity.agent_id] = identity
