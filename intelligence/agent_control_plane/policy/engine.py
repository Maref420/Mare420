from intelligence.agent_control_plane.permissions.models import Capability


class AgentPolicyEngine:
    """Enforce immutable behavioral boundaries."""

    def validate(self, capability: Capability) -> None:
        allowed = {
            Capability.MEMORY_RETRIEVE,
            Capability.MEMORY_STORE,
            Capability.MEMORY_FORGET,
        }

        if capability not in allowed:
            raise PermissionError("Policy rejected capability.")
