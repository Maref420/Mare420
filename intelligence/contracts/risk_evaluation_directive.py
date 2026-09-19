"""
Risk Evaluation Directive Schema for Downstream Risk Agents.
Defines the strict, immutable contract between Control Plane and Risk Agents.
Governed by: Principle of Least Privilege & Contract Purity.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RiskEvaluationDirective(BaseModel):
    """
    Immutable directive sent to Risk Agents after Policy approval.
    Contains only fields necessary for risk assessment and position sizing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    directive_id: str = Field(..., min_length=1)
    source_proposal_id: str = Field(..., min_length=1)
    target_agent_family: Literal["RISK"] = "RISK"
    symbol: str = Field(..., min_length=1, max_length=32)
    proposed_action: str = Field(..., min_length=1)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    adversarial_survival_score: float = Field(..., ge=0.0, le=1.0)
    regime_compatibility: float = Field(..., ge=0.0, le=1.0)
    requires_human_approval: bool
    trace_id: str = Field(..., min_length=1)
    timestamp_ns: int = Field(..., gt=0)
    audit_log_ref: str = Field(..., min_length=1)
