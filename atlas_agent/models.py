"""
Data Models for ATLAS AI Agent
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime

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

class Requirement(BaseModel):
    description: str
    language: Language
    project_name: str
    target_folder: str
    additional_rules: List[str] = []
    constraints: Dict[str, Any] = {}

class Specification(BaseModel):
    requirement: Requirement
    architecture: str
    modules: List[Dict[str, Any]]
    dependencies: List[str]
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None

class SecurityFinding(BaseModel):
    severity: SecurityLevel
    category: str
    message: str
    file_path: str
    line_number: Optional[int] = None
    suggestion: str = ""

class TestResult(BaseModel):
    test_name: str
    passed: bool
    duration_ms: float
    output: str = ""
    errors: List[str] = []

class Artifact(BaseModel):
    requirement: Requirement
    specification: Optional[Specification] = None
    generated_files: List[str] = []
    dependencies: Dict[str, str] = {}
    security_findings: List[SecurityFinding] = []
    test_results: List[TestResult] = []
    status: ApprovalStatus = ApprovalStatus.PENDING
    timestamp: datetime = Field(default_factory=datetime.now)
    temp_dir: Optional[str] = None

class AuditLog(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    action: str
    component: str
    details: Dict[str, Any] = {}
    result: str = "success"
    error: Optional[str] = None
