from typing import ClassVar

from intelligence.agent_runtime.state.models import (
    AgentRuntimeState,
    RuntimeState,
)


class InvalidRuntimeStateTransitionError(ValueError):
    """Raised when a runtime state transition is not permitted."""


InvalidRuntimeStateTransition = InvalidRuntimeStateTransitionError


class AgentRuntimeStateManager:
    """Controlled state machine for Agent Runtime execution state."""

    _TRANSITIONS: ClassVar[
        dict[RuntimeState, frozenset[RuntimeState]]
    ] = {
        RuntimeState.INITIALIZED: frozenset({RuntimeState.READY}),
        RuntimeState.READY: frozenset({RuntimeState.RUNNING}),
        RuntimeState.RUNNING: frozenset(
            {
                RuntimeState.PAUSED,
                RuntimeState.FAILED,
                RuntimeState.TERMINATED,
            }
        ),
        RuntimeState.PAUSED: frozenset(
            {
                RuntimeState.RUNNING,
                RuntimeState.FAILED,
                RuntimeState.TERMINATED,
            }
        ),
        RuntimeState.FAILED: frozenset({RuntimeState.TERMINATED}),
        RuntimeState.TERMINATED: frozenset(),
    }

    def __init__(self) -> None:
        self._states: dict[str, AgentRuntimeState] = {}

    def initialize(self, agent_id: str) -> AgentRuntimeState:
        if not agent_id:
            raise ValueError("agent_id must not be empty.")

        if agent_id in self._states:
            raise ValueError("Agent runtime state is already initialized.")

        state = AgentRuntimeState(
            agent_id=agent_id,
            state=RuntimeState.INITIALIZED,
        )
        self._states[agent_id] = state
        return state

    def get(self, agent_id: str) -> AgentRuntimeState | None:
        if not agent_id:
            raise ValueError("agent_id must not be empty.")
        return self._states.get(agent_id)

    def transition(
        self,
        agent_id: str,
        target_state: RuntimeState,
    ) -> AgentRuntimeState:
        current = self.get(agent_id)

        if current is None:
            raise KeyError("Unknown Agent runtime state.")

        allowed = self._TRANSITIONS[current.state]

        if target_state not in allowed:
            raise InvalidRuntimeStateTransitionError(
                f"Invalid runtime state transition: "
                f"{current.state.value} -> {target_state.value}"
            )

        updated = current.model_copy(update={"state": target_state})
        self._states[agent_id] = updated
        return updated
