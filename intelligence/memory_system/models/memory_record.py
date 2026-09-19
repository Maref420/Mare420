"""
Memory Record Contract for Atlas AI Memory Kernel.
Defines the strict schema for all memory types with full provenance.
Contains ZERO business logic.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from intelligence.contracts.unified_decision_proposal import (
    EpistemicStatus,
    FailureTaxonomy,
)


class MemoryType(StrEnum):
    """Supported memory subsystems."""

    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class ValidationStatus(StrEnum):
    """Lifecycle status of the memory record."""

    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"


class MemoryRecord(BaseModel):
    """
    Unified Memory Record with mandatory provenance.
    Frozen to prevent post-creation mutation (Governance Rule 10).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # --- Original Fields (Preserved for Backward Compatibility) ---
    memory_id: str = Field(min_length=1)
    memory_type: MemoryType
    created_at: datetime
    content: Any
    metadata: dict[str, Any] = Field(default_factory=dict)
    validation_status: ValidationStatus
    operation_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)

    # --- New Provenance Fields (Phase 2 Upgrade) ---
    # Default values provided ONLY to prevent breaking existing instantiation
    # in experience_engine and stores. Agents MUST provide real values.

    source: str = Field(
        default="UNKNOWN_SOURCE",
        description="Origin of the data (Rule 4: Memory Provenance)",
    )
    source_type: str = Field(
        default="UNKNOWN_TYPE",
        description="Classification of the source system",
    )
    regime: str = Field(
        default="UNKNOWN_REGIME",
        description="Market/System regime at creation time",
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="List of Evidence IDs backing this memory (Rule 3)",
    )
    epistemic_status: EpistemicStatus = Field(
        default=EpistemicStatus.UNKNOWN,
        description="Anti-hallucination state (Rule 2)",
    )
    failure_taxonomy: FailureTaxonomy = Field(
        default=FailureTaxonomy.NONE,
        description="Failure classification if applicable (Rule 10)",
    )

    def to_json(self) -> str:
        """Compatibility method matching contract adapter patterns."""
        return self.model_dump_json(exclude_none=True)

    @classmethod
    def from_json(cls, raw: str) -> MemoryRecord:
        """Compatibility method matching contract adapter patterns."""
        return cls.model_validate_json(raw)
