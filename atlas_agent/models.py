from typing import Any, Optional
from enum import Enum
from datetime import datetime, timezone
from uuid import UUID, uuid4
"""
Data Models for ATLAS AI Agent
"""
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, ConfigDict, field_validator


class Language(StrEnum):
    PYTHON = "python"
    RUST = "rust"
    GO = "go"

class SecurityLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class CodingLoopStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    LOOP_EXHAUSTED = "loop_exhausted"

class Requirement(BaseModel):
    description: str
    language: Language
    project_name: str
    target_folder: str
    additional_rules: list[str] = []
    constraints: dict[str, Any] = {}

class Specification(BaseModel):
    requirement: Requirement
    architecture: str
    modules: list[dict[str, Any]]
    dependencies: list[str]
    approved_by: str | None = None
    approved_at: datetime | None = None

class SecurityLevel(str, Enum):
    """Enum governed by security-finding-v1.json severity_enum rule."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class SecurityFinding(BaseModel):
    """Security finding matching security-finding-v1.json contract.

    GOVERNANCE ENFORCEMENT:
    - extra='forbid': no parallel fields allowed
    - frozen=True: findings are immutable once created
    - file_path validated as relative path
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    severity: SecurityLevel
    category: str = Field(min_length=1)
    message: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    line_number: Optional[int] = Field(default=None, ge=0)
    suggestion: str = Field(min_length=1)

    @field_validator("file_path")
    @classmethod
    def validate_relative_path(cls, v: str) -> str:
        if v.startswith("/") or (":" in v.split("/")[0] and not v.startswith("./")):
            raise ValueError(f"file_path must be relative, got absolute: {v}")
        return v


class TestResult(BaseModel):
    test_name: str
    passed: bool
    duration_ms: float
    output: str = ""
    errors: list[str] = []

class Artifact(BaseModel):
    requirement: Requirement
    specification: Specification | None = None
    generated_files: list[str] = []
    dependencies: dict[str, str] = {}
    security_findings: list[SecurityFinding] = []
    test_results: list[TestResult] = []
    status: ApprovalStatus = ApprovalStatus.PENDING
    timestamp: datetime = Field(default_factory=datetime.now)
    temp_dir: str | None = None

class AuditLog(BaseModel):
    """Immutable audit record matching audit_events table and audit-contract-v1.json.

    GOVERNANCE ENFORCEMENT:
    - extra='forbid': rejects unknown fields (matches DB immutable policy)
    - frozen=True: enforces immutability at Python level
    - All required_fields from contract are present with correct types
    - Legacy fields (component, details, error) moved to metadata dict
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    contract_version: str = Field(default="1.0", pattern=r"^\d+\.\d+$")
    event_type: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    result: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


