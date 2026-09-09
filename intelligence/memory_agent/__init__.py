# MODULE: atlas-memory-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
from .store import GovernedMemoryStore, MemoryStoreError, CircuitState
from .bridge import RustIpcBridge
from .integration import (
    enrich_signal_from_memory,
    write_signal_to_memory,
    get_exchange_quality,
    set_exchange_quality,
)
from .replay import AgentSelfAudit, IpcReplayClient
from .protocol import (
    SignalNode,
    SignalPriority,
    SignalStatus,
    AgentMessage,
)
from .orchestrator import MemoryGraphAgent
from .neural import NeuralRouter, SynapseConfig

__all__ = [
    "GovernedMemoryStore",
    "MemoryStoreError",
    "CircuitState",
    "RustIpcBridge",
    "enrich_signal_from_memory",
    "write_signal_to_memory",
    "get_exchange_quality",
    "set_exchange_quality",
    "AgentSelfAudit",
    "IpcReplayClient",
    "SignalNode",
    "SignalPriority",
    "SignalStatus",
    "AgentMessage",
    "MemoryGraphAgent",
    "NeuralRouter",
    "SynapseConfig",
]
