"""
Governance Engine for ATLAS AI Agent
Enforces ATLAS AI Governance Rules
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from .models import AuditLog, SecurityFinding, SecurityLevel, Artifact, Specification, ApprovalStatus
from .config import settings
import json
import os
import re

class GovernanceEngine:
    """
    Enforces governance rules, policies, and audit logging.
    """

    def __init__(self):
        self.audit_logs: List[AuditLog] = []
        self._ensure_logs_dir()

    def _ensure_logs_dir(self):
        os.makedirs(settings.logs_dir, exist_ok=True)

    def log_audit(self, action: str, component: str, details: Dict[str, Any] = None, result: str = "success", error: str = None):
        log_entry = AuditLog(
            action=action,
            component=component,
            details=details or {},
            result=result,
            error=error
        )
        self.audit_logs.append(log_entry)

        log_file = os.path.join(settings.logs_dir, "audit.log")
        with open(log_file, "a") as f:
            f.write(f"{log_entry.timestamp} | {action} | {component} | {result} | {error or ''}\n")

    def check_policy(self, policy_name: str, context: Dict[str, Any]) -> bool:
        self.log_audit("policy_check", "governance", {"policy": policy_name, "context": str(context)})

        if policy_name == "architecture_first":
            if not context.get("architecture"):
                self.log_audit("policy_failed", "governance", {"policy": policy_name}, result="failed", error="Missing architecture")
                return False
        elif policy_name == "spec_before_code":
            if not context.get("specification"):
                self.log_audit("policy_failed", "governance", {"policy": policy_name}, result="failed", error="Missing specification")
                return False
        elif policy_name == "security_first":
            if not context.get("security_scan"):
                self.log_audit("policy_failed", "governance", {"policy": policy_name}, result="failed", error="Missing security scan")
                return False

        return True

    def validate_specification(self, spec: Specification) -> bool:
        self.log_audit("spec_validation", "governance", {"spec": spec.model_dump_json()})

        if not spec.architecture:
            self.log_audit("spec_validation_failed", "governance", error="Missing architecture")
            return False

        if not spec.modules:
            self.log_audit("spec_validation_failed", "governance", error="Missing modules")
            return False

        return True

    def scan_for_secrets(self, content: str, file_path: str) -> List[SecurityFinding]:
        findings = []
        for pattern in settings.secret_patterns:
            if re.search(pattern, content):
                findings.append(SecurityFinding(
                    severity=SecurityLevel.CRITICAL,
                    category="secret_detection",
                    message=f"Potential secret found: {pattern}",
                    file_path=file_path,
                    suggestion="Remove secret and use environment variable or secret manager"
                ))
        return findings

    def validate_artifact(self, artifact: Artifact) -> bool:
        self.log_audit("artifact_validation", "governance", {"artifact": artifact.model_dump_json()})

        critical_findings = [f for f in artifact.security_findings if f.severity == SecurityLevel.CRITICAL]
        if critical_findings:
            self.log_audit("artifact_validation_failed", "governance", error="Critical security findings")
            return False

        failed_tests = [t for t in artifact.test_results if not t.passed]
        if failed_tests:
            self.log_audit("artifact_validation_failed", "governance", error="Failed tests")
            return False

        return True

    def require_human_approval(self, artifact: Artifact) -> bool:
        if not settings.require_human_approval:
            return True

        print("\n🔒 Human Approval Required")
        print(f"Artifact: {artifact.requirement.project_name}")
        print(f"Status: {artifact.status.value}")
        print(f"Security Findings: {len(artifact.security_findings)}")
        print(f"Test Results: {len(artifact.test_results)}")
        print("\nDo you approve this artifact? (yes/no)")

        try:
            response = input("> ").strip().lower()
            if response == "yes":
                artifact.status = ApprovalStatus.APPROVED
                self.log_audit("human_approval", "governance", {"artifact": artifact.requirement.project_name}, result="approved")
                return True
            else:
                artifact.status = ApprovalStatus.REJECTED
                self.log_audit("human_rejection", "governance", {"artifact": artifact.requirement.project_name}, result="rejected")
                return False
        except EOFError:
            return False
