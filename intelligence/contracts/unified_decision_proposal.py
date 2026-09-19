"""
Unified Decision Proposal Contract for Atlas AI.
Strictly defines the cross-language boundary types between
Python AI Agents and Rust Control Plane.
Contains ZERO business logic.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EpistemicStatus(StrEnum):
    """Rule 2: Anti-Hallucination. UNKNOWN must never map to FACT."""

    UNKNOWN = "UNKNOWN"
    HYPOTHESIS = "HYPOTHESIS"
    INFERENCE = "INFERENCE"
    FACT = "FACT"


class ProposalStatus(StrEnum):
    """Rule 9: Standardized Agent Output Statuses."""

    OBSERVED = "OBSERVED"
    ANALYZED = "ANALYZED"
    HYPOTHESIS = "HYPOTHESIS"
    VERIFIED = "VERIFIED"
    CONFLICTED = "CONFLICTED"
    INSUFFICIENT = "INSUFFICIENT"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    ESCALATED = "ESCALATED"
    PROPOSAL = "PROPOSAL"


class FailureTaxonomy(StrEnum):
    """Rule 10: Standardized Failure Codes for Failure Memory."""

    F01_HALLUCINATION = "F01"
    F02_UNSUPPORTED_CLAIM = "F02"
    F03_WRONG_EVIDENCE = "F03"
    F04_STALE_EVIDENCE = "F04"
    F05_DATA_MISINTERPRETATION = "F05"
    F06_CONTRADICTION_IGNORED = "F06"
    F07_CONFIDENCE_MISCALIBRATION = "F07"
    F08_TOOL_MISUSE = "F08"
    F09_CONTRACT_VIOLATION = "F09"
    F10_PERMISSION_VIOLATION = "F10"
    F11_SCOPE_VIOLATION = "F11"
    F12_MEMORY_CONTAMINATION = "F12"
    F13_REASONING_ERROR = "F13"
    F14_VALIDATION_BYPASS = "F14"
    F15_POLICY_VIOLATION = "F15"
    F16_EXECUTION_ATTEMPT = "F16"
    NONE = "NONE"


class ConfidenceVector(BaseModel):
    """Rule 7: Multi-dimensional trust metric. No single scalar allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_quality: float = Field(ge=0.0, le=1.0)
    source_reliability: float = Field(ge=0.0, le=1.0)
    data_freshness: float = Field(ge=0.0, le=1.0)
    cross_validation: float = Field(ge=0.0, le=1.0)
    historical_accuracy: float = Field(ge=0.0, le=1.0)
    regime_compatibility: float = Field(ge=0.0, le=1.0)
    contradiction_level: float = Field(ge=0.0, le=1.0)
    adversarial_survival: float = Field(ge=0.0, le=1.0)
    risk_compatibility: float = Field(ge=0.0, le=1.0)


class EvidenceRecord(BaseModel):
    """Rule 3: Every claim requires provenance-backed evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    timestamp_ns: int = Field(ge=1)
    quality_score: float = Field(ge=0.0, le=1.0)
    reliability_score: float = Field(ge=0.0, le=1.0)
    cross_check_status: str = Field(min_length=1)


class MemoryProvenance(BaseModel):
    """Rule 4: Memory records must carry full context, not just raw data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str = Field(min_length=1)
    memory_type: str = Field(min_length=1)
    retrieved_context: str
    regime_at_creation: str
    failure_count: int = Field(ge=0)
    status: str = Field(min_length=1)


class AdversarialValidation(BaseModel):
    """Rule 6: Mandatory independent validation before Control Plane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tested_by_agent: str = Field(min_length=1)
    overfitting_detected: bool
    regime_failure_risk: float = Field(ge=0.0, le=1.0)
    data_leakage_risk: float = Field(ge=0.0, le=1.0)
    survival_score: float = Field(ge=0.0, le=1.0)


class ContradictionReport(BaseModel):
    """Rule 11: Contradiction Engine output. NO_DECISION is a valid state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contradiction_detected: bool
    conflicting_agents: list[str] = Field(default_factory=list)
    resolution_method: str
    final_stance: str = Field(pattern=r"^(BULLISH|BEARISH|NEUTRAL|NO_DECISION)$")


class DecisionProposal(BaseModel):
    """
    The single unified structure for ALL outputs from
    Memory Layer and AI Agents heading to Control Plane.
    PROPOSAL != AUTHORIZATION.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # 1. Identity & Authority (Rule 8)
    proposal_id: str = Field(min_length=1)
    producer_agent_id: str = Field(min_length=1)
    agent_family: str = Field(
        pattern=r"^(OBSERVATION|INTELLIGENCE|RESEARCH|VALIDATION|DECISION)$"
    )
    timestamp_ns: int = Field(ge=1)

    # 2. Epistemic State (Rule 2)
    epistemic_status: EpistemicStatus
    proposal_status: ProposalStatus

    # 3. The Claim / Payload
    target_strategy: str = Field(min_length=1)
    proposed_action: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)

    # 4. Evidence & Provenance (Rule 3 & 4)
    required_evidence: list[EvidenceRecord] = Field(min_length=1)
    memory_provenance: list[MemoryProvenance] = Field(default_factory=list)

    # 5. Trust Metrics (Rule 7)
    confidence_vector: ConfidenceVector

    # 6. Validation & Safety (Rule 6)
    independent_validator_id: str | None = None
    adversarial_report: AdversarialValidation
    known_failures_from_memory: list[FailureTaxonomy] = Field(default_factory=list)

    # 7. Contradiction (Rule 11)
    contradiction_report: ContradictionReport

    # 8. Escalation & Audit (Governance Rules)
    requires_human_approval: bool
    audit_log_ref: str = Field(min_length=1)

    def to_json(self) -> str:
        """Compatibility method matching existing contract adapter patterns."""
        return self.model_dump_json(exclude_none=True)

    @classmethod
    def from_json(cls, raw: str) -> DecisionProposal:
        """Compatibility method matching existing contract adapter patterns."""
        return cls.model_validate_json(raw)
