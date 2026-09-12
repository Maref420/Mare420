"""Root Cause Analysis and Adversarial Validation engines.

Pillar 1: RCA - Analyzes WHY errors occurred, not just WHAT failed.
Pillar 3: Adversarial - Hostile reviewer finds edge cases before compile.

Governed by:
  - contracts/schemas/ai/root-cause-v1.json
  - contracts/schemas/ai/llm-invocation-v1.json

Privacy: Never sends source code to external LLM for analysis.
Only error messages and structural descriptions are sent.
"""
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

__all__ = ["RootCauseAnalyzer", "AdversarialReviewer", "RCAFinding", "RootCauseReport"]

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    MISSING_IMPORT = "missing_import"
    WRONG_TYPE = "wrong_type"
    LOGIC_ERROR = "logic_error"
    MISSING_IMPL = "missing_impl"
    API_MISMATCH = "api_mismatch"
    OWNERSHIP_ERROR = "ownership_error"
    LIFETIME_ERROR = "lifetime_error"
    SYNTAX_ERROR = "syntax_error"
    DEPENDENCY_MISSING = "dependency_missing"
    CONFIG_ERROR = "config_error"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"


@dataclass(frozen=True)
class RCAFinding:
    """A single root cause finding - safe for memory storage."""
    error_signature: str
    category: ErrorCategory
    root_cause: str
    fix_directive: str
    confidence: float
    severity: Severity


@dataclass
class RootCauseReport:
    """Structured RCA report for repair context injection."""
    errors_analyzed: int
    findings: list[RCAFinding] = field(default_factory=list)
    overall_assessment: str = ""
    recommended_strategy: str = "patch"

    def to_repair_context(self) -> str:
        """Convert to text block for repair prompt injection."""
        if not self.findings:
            return ""
        parts = ["\n=== ROOT CAUSE ANALYSIS ==="]
        parts.append(f"Assessment: {self.overall_assessment}")
        parts.append(f"Recommended strategy: {self.recommended_strategy}")
        parts.append("Findings:")
        for i, f in enumerate(self.findings[:10], 1):
            parts.append(
                f"  {i}. [{f.category.value}] {f.root_cause} "
                f"(conf={f.confidence:.0%}, sev={f.severity.value})"
            )
            parts.append(f"     Fix: {f.fix_directive}")
        return "\n".join(parts)


# Heuristic rules for local RCA without LLM call
_RCA_HEURISTICS: list[tuple[str, ErrorCategory, str, str]] = [
    ("cannot find value", ErrorCategory.MISSING_IMPORT,
     "Variable or function not defined in scope",
     "Add missing import or define the variable before use"),
    ("cannot find type", ErrorCategory.MISSING_IMPORT,
     "Type not found in current scope",
     "Import the type or check spelling"),
    ("mismatched types", ErrorCategory.WRONG_TYPE,
     "Type mismatch between expected and actual",
     "Convert to correct type or fix function signature"),
    ("expected.*found", ErrorCategory.WRONG_TYPE,
     "Wrong type provided to function or assignment",
     "Check function signature and provide correct type"),
    ("no method named", ErrorCategory.API_MISMATCH,
     "Method does not exist on this type",
     "Check available methods or implement the trait"),
    ("does not implement", ErrorCategory.MISSING_IMPL,
     "Required trait not implemented",
     "Implement the required trait for this type"),
    ("borrowed value does not live long enough", ErrorCategory.LIFETIME_ERROR,
     "Reference outlives the borrowed value",
     "Extend lifetime or clone/own the value"),
    ("cannot borrow.*as mutable", ErrorCategory.OWNERSHIP_ERROR,
     "Multiple mutable borrows or immutable+mutable conflict",
     "Use interior mutability (RefCell/Mutex) or restructure borrows"),
    ("use of moved value", ErrorCategory.OWNERSHIP_ERROR,
     "Value was moved and cannot be used again",
     "Clone the value before move or use references"),
    ("unresolved import", ErrorCategory.DEPENDENCY_MISSING,
     "Module or crate not found",
     "Add dependency to Cargo.toml or fix module path"),
    ("could not compile", ErrorCategory.CONFIG_ERROR,
     "Compilation configuration error",
     "Check Cargo.toml target sections and edition"),
    ("no targets specified", ErrorCategory.CONFIG_ERROR,
     "Cargo.toml missing target configuration",
     "Add [[bin]] or [lib] section with correct path"),
]


class RootCauseAnalyzer:
    """Analyzes WHY compilation/test errors occurred.

    Two modes:
    1. Local heuristic analysis (fast, no LLM needed)
    2. LLM-assisted deep analysis (slower, more accurate)

    Privacy-safe: only error messages are analyzed, never source code.
    """

    @classmethod
    def analyze_local(cls, errors: list[str], language: str) -> RootCauseReport:
        """Analyze errors using local heuristics - no LLM call needed.

        Fast fallback that categorizes common errors without external calls.
        """
        findings: list[RCAFinding] = []
        seen_sigs: set[str] = set()

        for error in errors[:20]:
            error_lower = error.lower()
            matched = False

            for pattern, category, cause, fix in _RCA_HEURISTICS:
                import re
                if re.search(pattern, error_lower):
                    sig = f"{category.value}:{error[:64]}"
                    if sig not in seen_sigs:
                        seen_sigs.add(sig)
                        severity = Severity.BLOCKER if category in (
                            ErrorCategory.MISSING_IMPORT,
                            ErrorCategory.CONFIG_ERROR,
                            ErrorCategory.DEPENDENCY_MISSING,
                        ) else Severity.MAJOR
                        findings.append(RCAFinding(
                            error_signature=error[:128],
                            category=category,
                            root_cause=cause[:256],
                            fix_directive=fix[:512],
                            confidence=0.7,
                            severity=severity,
                        ))
                    matched = True
                    break

            if not matched and error.strip():
                sig = f"unknown:{error[:64]}"
                if sig not in seen_sigs:
                    seen_sigs.add(sig)
                    findings.append(RCAFinding(
                        error_signature=error[:128],
                        category=ErrorCategory.UNKNOWN,
                        root_cause="Uncategorized error requiring manual review"[:256],
                        fix_directive="Review compiler error message carefully"[:512],
                        confidence=0.3,
                        severity=Severity.MINOR,
                    ))

        # Determine recommended strategy
        blocker_count = sum(1 for f in findings if f.severity == Severity.BLOCKER)
        total = len(findings)
        if blocker_count > 3 or total > 15:
            strategy = "rewrite"
            assessment = f"Many blockers ({blocker_count}) suggest fundamental issues. Consider rewrite."
        elif total <= 5:
            strategy = "patch"
            assessment = f"Few errors ({total}). Targeted patch should resolve them."
        else:
            strategy = "patch"
            assessment = f"Moderate errors ({total}). Patch with careful attention to each finding."

        report = RootCauseReport(
            errors_analyzed=len(errors),
            findings=findings,
            overall_assessment=assessment[:512],
            recommended_strategy=strategy,
        )
        logger.info("RCA local: %d errors -> %d findings, strategy=%s",
                     len(errors), len(findings), strategy)
        return report

    @classmethod
    def analyze_with_llm(cls, errors: list[str], language: str,
                         llm_client: Any) -> RootCauseReport:
        """Deep RCA using LLM - more accurate but slower.

        Only sends error messages, never source code.
        Falls back to local analysis if LLM fails.
        """
        if not errors:
            return RootCauseReport(errors_analyzed=0, findings=[],
                                   overall_assessment="No errors to analyze",
                                   recommended_strategy="patch")

        error_text = "\n".join(f"  {i+1}. {e[:200]}" for i, e in enumerate(errors[:15]))
        prompt = (
            f"You are a senior {language} compiler engineer performing root cause analysis.\n"
            f"Analyze these compilation/test errors and determine WHY they occurred.\n\n"
            f"ERRORS:\n{error_text}\n\n"
            f"Respond ONLY with valid JSON matching this schema:\n"
            f'{{"findings": [{{"category": "missing_import|wrong_type|logic_error|'
            f'missing_impl|api_mismatch|ownership_error|lifetime_error|syntax_error|'
            f'dependency_missing|config_error|unknown", '
            f'"root_cause": "brief explanation", '
            f'"fix_directive": "specific fix instruction", '
            f'"confidence": 0.0-1.0, '
            f'"severity": "blocker|major|minor"}}], '
            f'"overall_assessment": "summary", '
            f'"recommended_strategy": "patch|rewrite|different_approach"}}\n\n'
            f"Do NOT include any source code in your response."
        )

        try:
            response = llm_client.generate_code(prompt, "json")
            parsed = json.loads(response)
            findings = []
            for fd in parsed.get("findings", [])[:10]:
                try:
                    cat = ErrorCategory(fd.get("category", "unknown"))
                except ValueError:
                    cat = ErrorCategory.UNKNOWN
                try:
                    sev = Severity(fd.get("severity", "major"))
                except ValueError:
                    sev = Severity.MAJOR
                findings.append(RCAFinding(
                    error_signature=fd.get("root_cause", "")[:128],
                    category=cat,
                    root_cause=fd.get("root_cause", "Unknown")[:256],
                    fix_directive=fd.get("fix_directive", "Review manually")[:512],
                    confidence=max(0.0, min(1.0, float(fd.get("confidence", 0.5)))),
                    severity=sev,
                ))
            report = RootCauseReport(
                errors_analyzed=len(errors),
                findings=findings,
                overall_assessment=parsed.get("overall_assessment", "")[:512],
                recommended_strategy=parsed.get("recommended_strategy", "patch"),
            )
            logger.info("RCA LLM: %d errors -> %d findings", len(errors), len(findings))
            return report
        except (json.JSONDecodeError, KeyError, ValueError, Exception) as e:
            logger.warning("LLM RCA failed (%s), falling back to local", e)
            return cls.analyze_local(errors, language)


class AdversarialReviewer:
    """Hostile code reviewer that finds bugs before compilation.

    Uses a separate LLM call with adversarial persona to find:
    - Edge cases the original developer missed
    - Race conditions and concurrency issues
    - Logic errors not caught by static analysis
    - Security vulnerabilities beyond clippy

    Privacy-safe: sends structural description, not raw source code.
    Governed by: llm-invocation-v1.json privacy boundary.
    """

    ADVERSARIAL_PROMPT_TEMPLATE = (
        "You are a hostile senior code reviewer. Your job is to find bugs, "
        "security vulnerabilities, race conditions, and logic errors.\n\n"
        "LANGUAGE: {language}\n"
        "MODULE TYPE: {module_type}\n"
        "DESCRIPTION: {description}\n\n"
        "ERRORS FROM COMPILER/TESTS:\n{errors}\n\n"
        "Analyze what could go wrong. Focus on:\n"
        "1. Edge cases (empty input, max values, zero, negative)\n"
        "2. Overflow/underflow risks\n"
        "3. Missing error handling paths\n"
        "4. Incorrect assumptions about types or behavior\n"
        "5. Concurrency issues if applicable\n\n"
        "Respond ONLY with valid JSON:\n"
        '{{"findings": [{{"issue": "brief description", '
        '"severity": "blocker|major|minor", '
        '"suggestion": "how to fix"}}], '
        '"overall_risk": "low|medium|high|critical"}}\n\n'
        "Do NOT include any source code in your response."
    )

    @classmethod
    def review(cls, language: str, module_type: str, description: str,
               compile_errors: list[str], llm_client: Any) -> list[str]:
        """Run adversarial review and return findings as strings.

        Returns list of finding descriptions suitable for repair context.
        Falls back to empty list if LLM fails (never blocks pipeline).
        """
        error_text = "\n".join(compile_errors[:10]) if compile_errors else "No compile errors yet."
        prompt = cls.ADVERSARIAL_PROMPT_TEMPLATE.format(
            language=language,
            module_type=module_type[:64],
            description=description[:500],
            errors=error_text[:2000],
        )

        try:
            response = llm_client.generate_code(prompt, "json")
            parsed = json.loads(response)
            findings = []
            for f in parsed.get("findings", [])[:5]:
                issue = f.get("issue", "")[:200]
                suggestion = f.get("suggestion", "")[:300]
                severity = f.get("severity", "minor")
                if issue:
                    findings.append(
                        f"[ADVERSARIAL {severity.upper()}] {issue} -> {suggestion}"
                    )
            risk = parsed.get("overall_risk", "unknown")
            logger.info("Adversarial review: %d findings, risk=%s", len(findings), risk)
            return findings
        except (json.JSONDecodeError, KeyError, ValueError, Exception) as e:
            logger.warning("Adversarial review failed (non-blocking): %s", e)
            return []
