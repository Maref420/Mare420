"""
Governance Engine for ATLAS AI Agent
Enforces ATLAS AI Governance Rules
"""

__all__ = ['GovernanceEngine']

import logging
import os
import re
from typing import Any

from .config import settings
from .models import (
    ApprovalStatus,
    Artifact,
    AuditLog,
    SecurityFinding,
    SecurityLevel,
    Specification,
)


class GovernanceEngine:
    """
    Enforces governance rules, policies, and audit logging.
    """

    def __init__(self) -> None:
        self.audit_logs: list[AuditLog] = []
        self._ensure_logs_dir()

    def _ensure_logs_dir(self) -> None:
        os.makedirs(settings.logs_dir, exist_ok=True)

    def log_audit(
        self,
        action: str,
        component: str,
        details: dict[str, Any] | None = None,
        result: str = "success",
        error: str | None = None,
        event_type: str = "governance_event",
        operation_id: str = "unknown",
        agent_id: str = "governance_engine",
        resource: str = "",
    ) -> None:
        """Log an audit event using canonical AuditLog structure.

        Legacy params (component, details, error) are migrated to metadata.
        Governed by: contracts/schemas/audit/audit-contract-v1.json
        """
        metadata = dict(details or {})
        metadata["component"] = component
        if error is not None:
            metadata["error"] = error

        log_entry = AuditLog(
            event_type=event_type,
            operation_id=operation_id,
            agent_id=agent_id,
            action=action,
            resource=resource or component,
            result=result,
            metadata=metadata,
        )
        self.audit_logs.append(log_entry)
        log_file = os.path.join(settings.logs_dir, "audit.log")
        with open(log_file, "a") as f:
            f.write(f"{log_entry.timestamp} | {action} | {component} | {result} | {error or ''}\n")

    def check_policy(self, policy_name: str, context: dict[str, Any]) -> bool:
        self.log_audit("policy_check", "governance", {"policy": policy_name, "context": str(context)})

        if policy_name == "architecture_first":
            if not context.get("architecture"):
                self.log_audit("policy_failed", "governance", {"policy": policy_name}, result="failed", error="Missing architecture")
                return False
        elif policy_name == "spec_before_code":
            if not context.get("specification"):
                self.log_audit("policy_failed", "governance", {"policy": policy_name}, result="failed", error="Missing specification")
                return False
        elif policy_name == "security_first" and not context.get("security_scan"):
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

    def scan_for_secrets(self, content: str, file_path: str) -> list[SecurityFinding]:
        findings = []
        for pattern in settings.secret_patterns:
            if re.search(pattern, content, re.IGNORECASE):
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


# ════════════════════════════════════════════════════════════════════
# POLICY ENFORCER — Reads enforceable rules from PortableMemory
# and mechanically checks generated code against them.
# Separate from GovernanceEngine to prevent bloat and coupling.
# Single source of truth: KnowledgeEntry tags in portable_memory.
# ════════════════════════════════════════════════════════════════════

import re as _re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas_agent.self_correcting_loop.portable_memory import KnowledgeEntry

logger = logging.getLogger(__name__)


@dataclass
class PolicyViolation:
    """A single policy violation found during enforcement."""
    rule_key: str
    severity: str          # "block" | "warn"
    message: str
    file_path: str = ""
    line_number: int = 0
    matched_text: str = ""


@dataclass
class EnforcementResult:
    """Result of policy enforcement on an artifact."""
    passed: bool
    violations: list[PolicyViolation] = field(default_factory=list)
    rules_checked: int = 0

    @property
    def blocking_violations(self) -> list[PolicyViolation]:
        return [v for v in self.violations if v.severity == "block"]

    @property
    def warnings(self) -> list[PolicyViolation]:
        return [v for v in self.violations if v.severity == "warn"]


# ── Enforcement rules mapped to KnowledgeEntry keys ──
# Each rule: (regex_pattern, severity, description)
# These are mechanically checkable subsets of the knowledge entries.

_ENFORCE_RULES: dict[str, list[tuple[str, str, str]]] = {
    "rust.coding_standard": [
        (r'\bunwrap\(\)', "block", "unwrap() forbidden on request path; use Result<T,E>"),
        (r'\bexpect\(', "block", "expect() forbidden on request path; use Result<T,E>"),
        (r'\bpanic!\(', "warn", "panic!() should not be used on request paths"),
    ],
    "go.coding_standard": [
        (r'err\s*$', "warn", "Possible ignored error; always handle err explicitly"),
        (r'_\s*=\s*\w+\.\w+\(', "warn", "Possible ignored return value; check error handling"),
    ],
    "python.coding_standard": [
        (r'except\s*:', "block", "Bare except forbidden; use explicit exception types"),
        (r'except\s+Exception\s*:', "warn", "Broad except Exception; prefer specific types"),
        (r'\beval\(', "block", "eval() forbidden; security risk"),
        (r'\bexec\(', "block", "exec() forbidden; security risk"),
    ],
    "constitution.error_handling": [
        (r'except\s*:\s*pass', "block", "Swallowed error: except: pass is forbidden"),
        (r'except.*:\s*pass', "block", "Swallowed error: do not silently pass on exceptions"),
    ],
    "privacy.no_secrets_in_output": [
        (r'(?i)(api[_-]?key|password|secret|token)\s*=\s*["\'][^"\']+["\']', "block",
         "Hardcoded secret detected; use environment variables"),
    ],
}


class PolicyEnforcer:
    """Enforces knowledge-base policies on generated code artifacts.

    Reads enforceable KnowledgeEntry items from PortableMemory and
    applies mechanical checks (regex-based) to generated source files.

    This class does NOT define rules — it reads them from memory.
    The _ENFORCE_RULES map links KnowledgeEntry keys to checkable patterns.

    Usage:
        enforcer = PolicyEnforcer()
        result = enforcer.enforce(artifact_files, language, knowledge_entries)
        if not result.passed:
            for v in result.blocking_violations:
                logger.warning("Policy blocked: %s", v.message)
    """

    def __init__(self) -> None:
        self._rules = _ENFORCE_RULES

    def get_enforceable_keys(self, knowledge: dict[str, "KnowledgeEntry"]) -> list[str]:
        """Return keys of knowledge entries tagged with 'enforce'."""
        return [
            key for key, entry in knowledge.items()
            if entry.enabled and "enforce" in entry.tags
        ]

    def enforce(self, files: dict[str, str], language: str,
                knowledge: dict[str, "KnowledgeEntry"]) -> EnforcementResult:
        """Check generated files against enforceable knowledge rules.

        Args:
            files: mapping of filename -> source code content
            language: target language ("rust", "go", "python")
            knowledge: the _knowledge dict from PortableMemory

        Returns:
            EnforcementResult with all violations found
        """
        lang = language.lower().strip()
        enforceable_keys = self.get_enforceable_keys(knowledge)
        violations: list[PolicyViolation] = []
        rules_checked = 0

        for key in enforceable_keys:
            entry = knowledge.get(key)
            if not entry:
                continue

            # Only apply language-specific rules to matching language
            if entry.language not in ("*", lang):
                continue

            patterns = self._rules.get(key, [])
            if not patterns:
                continue

            rules_checked += 1
            for pattern, severity, description in patterns:
                try:
                    compiled = _re.compile(pattern, _re.MULTILINE)
                except _re.error:
                    logger.warning("Invalid regex in policy rule %s: %s", key, pattern)
                    continue

                for filepath, content in files.items():
                    for line_num, line in enumerate(content.splitlines(), 1):
                        match = compiled.search(line)
                        if match:
                            violations.append(PolicyViolation(
                                rule_key=key,
                                severity=severity,
                                message=f"[{key}] {description}",
                                file_path=filepath,
                                line_number=line_num,
                                matched_text=match.group()[:80],
                            ))

        blocking = [v for v in violations if v.severity == "block"]
        passed = len(blocking) == 0

        if violations:
            logger.info("Policy enforcement: %d rules checked, %d violations (%d blocking)",
                       rules_checked, len(violations), len(blocking))
            for v in blocking:
                logger.warning("BLOCKED by policy: %s at %s:%d",
                             v.rule_key, v.file_path, v.line_number)

        return EnforcementResult(
            passed=passed,
            violations=violations,
            rules_checked=rules_checked,
        )

    def format_violations_for_repair(self, result: EnforcementResult) -> list[str]:
        """Format violations as repair hints for LLM injection.

        Converts PolicyViolations into strings suitable for repair_hints
        so the LLM knows exactly what to fix.
        """
        hints: list[str] = []
        for v in result.violations:
            prefix = "MUST FIX" if v.severity == "block" else "SHOULD FIX"
            loc = f"{v.file_path}:{v.line_number}" if v.file_path else ""
            hints.append(f"[{prefix}] {loc} {v.message} (matched: '{v.matched_text}')")
        return hints
