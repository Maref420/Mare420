"""
Public API Schemas for Atlas AI Observability Dashboard.
Frozen Pydantic V2 models ensuring Contract Purity.
Governed by: C-G3-3 (Contract Purity), C-G3-6 (Sensitive Data Prohibited).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PipelineHealthResponse(BaseModel):
    """System health status for SLA proof."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = Field(..., description="Overall system status")
    memory_system_initialized: bool
    hook_initialized: bool
    storage_backend: str = Field(..., description="Active storage type")
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class MemoryStatsResponse(BaseModel):
    """Memory tier statistics demonstrating learning capacity."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_records: int
    working_count: int
    episodic_count: int
    semantic_count: int
    procedural_count: int
    last_consolidation: str | None = None


class AuditEventResponse(BaseModel):
    """Sanitized audit event for compliance demonstration.
    Governed by: lifecycle-policy.yaml -> sensitive_data_logging: prohibited
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    event_type: str
    operation_id: str
    agent_id: str
    timestamp: datetime
    action: str
    resource: str
    result: str
    # metadata intentionally excluded or sanitized per C-G3-6


class CancelledSignalResponse(BaseModel):
    """Cancelled/Denied signal record proving filter rate."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    symbol: str
    action: str
    decision: str
    reason: str
    survival_score: float
    created_at: datetime
