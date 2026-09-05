from typing import Any, Optional
from enum import Enum
from datetime import datetime, timezone
from uuid import UUID, uuid4
"""
Data Models for ATLAS AI Agent
"""

__all__ = ['Requirement', 'Language', 'SecurityLevel', 'ArtifactStatus', 'GeneratedArtifact', 'ApprovalStatus', 'DeploymentRecord']

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
    DEPLOYED = "deployed"
    DEPLOY_FAILED = "deploy_failed"
    ROLLED_BACK = "rolled_back"

class CodingLoopStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    LOOP_EXHAUSTED = "loop_exhausted"

class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)

    description: str
    language: Language
    project_name: str
    target_folder: str
    additional_rules: list[str] = []
    constraints: dict[str, Any] = {}

class Specification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)

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
    model_config = ConfigDict(extra="forbid", frozen=False)

    test_name: str
    passed: bool
    duration_ms: float
    output: str = ""
    errors: list[str] = []

class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)

    requirement: Requirement
    specification: Specification | None = None
    generated_files: list[str] = []
    dependencies: dict[str, str] = {}
    security_findings: list[SecurityFinding] = []
    test_results: list[TestResult] = []
    status: ApprovalStatus = ApprovalStatus.PENDING
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # NOTE: temp_dir is FORBIDDEN as top-level field per artifact-v1.json contract.
    # Use metadata={"temp_dir": "..."} instead.

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



# ============================================================
# Execution Order Model v1.0
# Source: contracts/schemas/execution/order-v1.json
# Owner: Execution Engine (Rust). Python side is READ-ONLY consumer.
# ADR-001: This is NOT the same as agent_runtime execution (Layer 1).
# ============================================================

class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"

class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LIMIT = "stop_limit"
    STOP_MARKET = "stop_market"

class TimeInForce(StrEnum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    GTD = "gtd"

class Order(BaseModel):
    """Trade order matching order-v1.json contract.
    GOVERNANCE ENFORCEMENT:
    - extra="forbid": rejects unknown fields per order-v1.json rules
    - frozen=True: immutable after creation per immutable_after_submission
    - price required for limit/stop_limit orders validated in model_validator
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID = Field(default_factory=uuid4)
    symbol: str = Field(min_length=1)
    side: OrderSide
    quantity: float = Field(gt=0)
    order_type: OrderType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_id: str = Field(min_length=1)
    price: Optional[float] = Field(default=None, gt=0)
    stop_price: Optional[float] = Field(default=None, gt=0)
    time_in_force: Optional[TimeInForce] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol", "agent_id")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field must not be empty or whitespace-only")
        return v

# ============================================================
# Engine Message Envelope v1.0
# Source: governance/schemas/engine-contract-v1.json
# Purpose: Cross-engine message format for Go Broker communication
# ============================================================

class MessageMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    specification_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    validation_status: str = Field(min_length=1)

class EngineMessage(BaseModel):
    """Cross-engine message envelope matching engine-contract-v1.json.
    Used for publishing to Go Message Broker /publish endpoint.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: str = Field(default="1.0", pattern=r"^\d+\.\d+$")
    message_type: str = Field(min_length=1)
    source_engine: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any]
    metadata: MessageMetadata

    @classmethod
    def wrap_order(cls, order: Order, agent_id: str) -> "EngineMessage":
        """Create an EngineMessage wrapping an Order for broker publication."""
        return cls(
            message_type="exec.order.v1",
            source_engine="python_engine",
            payload=order.model_dump(mode="json"),
            metadata=MessageMetadata(
                specification_id="order-v1",
                policy_version="1.0",
                owner="Python AI Agent",
                validation_status="validated",
            ),
        )

class DeploymentRecord(BaseModel):
    """Immutable deployment record per CONSTITUTION.md §2 and deployment-record-v1.json."""
    deployment_id: str = Field(min_length=1)
    artifact_path: str = Field(min_length=1)
    target_path: str = Field(min_length=1)
    status: ApprovalStatus
    timestamp: float
    backup_path: Optional[str] = None
    post_deploy_validation: dict = Field(default_factory=dict)
    audit_event_id: str = Field(min_length=1)
    rollback_reason: Optional[str] = None

    model_config = ConfigDict(frozen=True)
