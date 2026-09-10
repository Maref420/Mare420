# MODULE: atlas-memory-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
from .bridge import RustIpcBridge
from .integration import (
    enrich_signal_from_memory,
    get_exchange_quality,
    set_exchange_quality,
    write_signal_to_memory,
)
from .neural import NeuralRouter, SynapseConfig
from .orchestrator import MemoryGraphAgent
from .protocol import (
    AgentMessage,
    SignalNode,
    SignalPriority,
    SignalStatus,
)
from .replay import AgentSelfAudit, IpcReplayClient
from .store import CircuitState, GovernedMemoryStore, MemoryStoreError

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
