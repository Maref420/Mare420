from intelligence.agent_control_plane.permissions.models import (
    Capability,
    PermissionSet,
)


class PermissionEngine:
    """Enforce explicit Agent capabilities."""

    def __init__(self) -> None:
        self._permissions: dict[str, PermissionSet] = {}

    def grant(self, permissions: PermissionSet) -> None:
        self._permissions[permissions.agent_id] = permissions

    def require(self, agent_id: str, capability: Capability) -> None:
        permissions = self._permissions.get(agent_id)

        if permissions is None:
            raise PermissionError("Agent has no registered permissions.")

        if capability not in permissions.capabilities:
            raise PermissionError(
                f"Agent lacks capability: {capability.value}"
            )
