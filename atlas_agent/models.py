"""
Data Models for ATLAS AI Agent
"""
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Language(str, Enum):
    PYTHON = "python"
    RUST = "rust"
    GO = "go"

class SecurityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class CodingLoopStatus(str, Enum):
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

class SecurityFinding(BaseModel):
    severity: SecurityLevel
    category: str
    message: str
    file_path: str
    line_number: int | None = None
    suggestion: str = ""

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
    timestamp: datetime = Field(default_factory=datetime.now)
    action: str
    component: str
    details: dict[str, Any] = {}
    result: str = "success"
    error: str | None = None
