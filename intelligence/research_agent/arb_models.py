# MODULE: atlas-research-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# CONTRACT: Models for receiving ArbitragePath from Go Gateway via WS.
# POLICY: Frozen models. source_uri mandatory per ADR-006.
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ArbitragePath(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchanges: list[str] = Field(..., min_length=2)
    symbol: str = Field(..., min_length=1)
    net_weight: float
    hop_count: int = Field(..., ge=1)
    profitable: bool
    timestamp_ns: int = Field(..., gt=0)
    source_uri: str = Field(..., min_length=1, description="Mandatory per ADR-006")


class ArbIpcMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    msg_type: str
    payload: ArbitragePath
    trace_id: str = Field(..., min_length=1)
    timestamp_ns: int = Field(..., gt=0)
    source_uri: str = Field(..., min_length=1, description="Mandatory per ADR-006")
