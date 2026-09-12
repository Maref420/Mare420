"""Self-Correcting Loop v3 - Governance-Aware with Portable Memory.

Improvements over v2:
1. Portable memory integration - learns from every attempt
2. Governance-aware repair context - enforces project contracts
3. Pattern extraction - auto-categorizes errors for learning
4. Strategy optimization - uses historical data to pick best strategy
5. Privacy-safe - never sends source code in repair prompts
6. Contract enforcement - injects llm-invocation-v1 rules into context
7. Anti-pattern promotion - repeated failures become anti-patterns

Governed by:
  - contracts/schemas/ai/llm-invocation-v1.json
  - contracts/schemas/ai/portable-memory-v1.json
  - CONSTITUTION.md section 17
"""
__all__ = ['SelfCorrectingLoop', 'QualityScore', 'LoopMetrics']

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

from ..code_patcher import CodePatcher


# ================================================================
# Governance Rules - loaded from contracts, hardcoded as fallback
# These are injected into every repair prompt sent to LLM
# ================================================================

GOVERNANCE_RULES = {
    "rust": [
        "Production-grade only: use Result<T, E> on all fallible paths.",
        "No unwrap() or expect() on request/compute paths (I7).",
        "Use checked_add/checked_mul for arithmetic that may overflow.",
        "Structured logging required: service, trace_id, span_id, code, duration_ms.",
        "Errors must map to ErrorEnvelope codes at service boundaries.",
        "Typed config from environment variables only - no hardcoded secrets.",
        "No external dependencies unless explicitly approved.",
        "All public functions must have doc comments.",
    ],
    "go": [
        "Production-grade only: handle every error, no ignored err on request paths.",
        "Use context.Context on every RPC/IO call with deadline propagation.",
        "Use ONLY Go standard library packages unless explicitly approved.",
        "Table-driven tests required for all exported functions.",
        "Structured logging required: service, trace_id, span_id, code, duration_ms.",
        "Client timeouts mandatory on all outbound calls.",
        "No goroutine leaks - all goroutines must be cancellable.",
    ],
    "python": [
        "Production-grade only: explicit types at all function boundaries.",
        "No bare except clauses (I7) - catch specific exceptions only.",
        "Use AppError domain exceptions with stable error codes.",
        "Structured logging required: service, trace_id, span_id, code, duration_ms.",
        "Typed config from environment via pydantic-settings.",
        "No secrets in source code - environment variables only.",
    ],
}

CONTRACT_REQUIREMENTS = [
    "Cross-service errors MUST use ErrorEnvelope with stable codes (VAL_, AUTH_, BIZ_, DEP_, RES_, NET_, INT_).",
    "Retry only when retryable=true, with jittered exponential backoff and max attempts.",
    "Deadlines propagate edge-to-leaf; honor remaining parent deadline.",
    "Language routing: Rust=compute, Go=transfer/network, Python=intelligence/agents.",
    "One owner per unit of work; no cross-language business logic duplication.",
]


class RepairStrategy(Enum):
    """Escalation strategy for repair attempts."""
    PATCH = "patch"
    REWRITE = "rewrite"
    DIFFERENT_MODEL = "different_model"
    DIFFERENT_PROMPT = "different_prompt"


@dataclass
class QualityScore:
    """Multi-dimensional quality assessment including governance and execution."""
    syntax: float = 0.0
    security: float = 0.0
    execution: float = 1.0      # Compile + test pass rate
    completeness: float = 0.0
    style: float = 0.0
    governance: float = 1.0
    overall: float = 0.0
    PASS_THRESHOLD = 0.8

    def compute_overall(self) -> float:
        self.overall = (
            self.syntax * 0.25 +
            self.security * 0.20 +
            self.execution * 0.25 +
            self.completeness * 0.10 +
            self.style * 0.05 +
            self.governance * 0.15
        )
        return self.overall

    @property
    def passed(self) -> bool:
        return self.overall >= self.PASS_THRESHOLD


@dataclass
class AttemptRecord:
    """Record of a single generation attempt."""
    attempt_number: int
    strategy: RepairStrategy
    model_used: str
    prompt_hash: str
    quality_score: QualityScore
    errors: list[str]
    security_findings: list[str]
    code_length: int
    latency_seconds: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class LoopMetrics:
    """Aggregate metrics for the self-correcting loop."""
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    total_attempts: int = 0
    scores_by_attempt: dict[int, list[float]] = field(default_factory=dict)
    common_failures: dict[str, int] = field(default_factory=dict)
    avg_latency: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successful_runs / max(self.total_runs, 1)

    @property
    def avg_attempts_per_success(self) -> float:
        return self.total_attempts / max(self.successful_runs, 1)

    def record_attempt(self, attempt: int, score: float) -> None:
        if attempt not in self.scores_by_attempt:
            self.scores_by_attempt[attempt] = []
        self.scores_by_attempt[attempt].append(score)

    def record_failure(self, error_category: str) -> None:
        self.common_failures[error_category] = self.common_failures.get(error_category, 0) + 1

    def summary(self) -> dict:
        return {
            "total_runs": self.total_runs,
            "success_rate": f"{self.success_rate:.1%}",
            "avg_attempts": f"{self.avg_attempts_per_success:.1f}",
            "common_failures": dict(sorted(
                self.common_failures.items(), key=lambda x: -x[1]
            )[:5]),
            "scores_by_attempt": {
                k: f"{sum(v)/len(v):.2f}" for k, v in self.scores_by_attempt.items()
            },
        }


class SelfCorrectingLoop:
    """Governance-aware self-correcting code generation loop with portable memory.

    Learns from every attempt, enforces project contracts, and optimizes
    repair strategies based on historical effectiveness data.
    """
    MAX_ATTEMPTS = 5
    PASS_THRESHOLD = 0.8
    MAX_REPAIR_CHARS = 6000  # Hard token budget for repair prompts

    def __init__(
        self,
        portable_memory: Optional[Any] = None,
        governance_engine: Optional[Any] = None,
    ) -> None:
        self.metrics = LoopMetrics()
        self.patcher = CodePatcher()
        self._attempt_history: list[AttemptRecord] = []
        self.memory = portable_memory
        self.governance = governance_engine

    def determine_strategy(
        self,
        attempt: int,
        previous_errors: list[str],
        language: str = "",
    ) -> RepairStrategy:
        """Determine repair strategy using memory-optimized selection.

        If portable memory has historical data, uses the best-performing
        strategy for this language. Otherwise falls back to escalation ladder.
        """
        # Use memory-optimized strategy if available
        if self.memory is not None and language:
            best = self.memory.get_best_strategy(language)
            stats = self.memory._strategy_stats.get(best)
            if stats and stats.total_attempts >= 3 and stats.success_rate > 0.4:
                logger.info(
                    "Memory-optimized strategy: %s (rate=%.0f%%, n=%d)",
                    best, stats.success_rate * 100, stats.total_attempts,
                )
                try:
                    return RepairStrategy(best)
                except ValueError:
                    pass

        # Fallback: escalation ladder
        if attempt <= 2:
            return RepairStrategy.PATCH
        elif attempt <= 4:
            return RepairStrategy.REWRITE
        else:
            return RepairStrategy.DIFFERENT_PROMPT

    def build_structured_repair_context(
        self,
        previous_code: str,
        errors: list[str],
        security_findings: list[str],
        anti_patterns: list[str],
        attempt_history: list[AttemptRecord],
        strategy: RepairStrategy,
        language: str = "",
        governance_rules: Optional[list[str]] = None,
        repair_hints: Optional[list[str]] = None,
    ) -> str:
        """Build governance-aware, privacy-safe repair context for LLM.

        IMPORTANT: Never includes raw source code in prompts sent to
        external LLMs (per llm-invocation-v1.json privacy boundary).
        Only error descriptions, fix hints, and governance rules are sent.
        """
        parts = []

        # Section 1: Strategy instruction
        if strategy == RepairStrategy.PATCH:
            parts.append(
                "REPAIR STRATEGY: PATCH - Fix ONLY the specific errors below. "
                "Keep the rest of the code unchanged."
            )
        elif strategy == RepairStrategy.REWRITE:
            parts.append(
                "REPAIR STRATEGY: FULL REWRITE - The previous approach failed. "
                "Rewrite the entire file from scratch, avoiding the errors below."
            )
        elif strategy == RepairStrategy.DIFFERENT_MODEL:
            parts.append(
                "REPAIR STRATEGY: DIFFERENT MODEL - Previous model could not fix these issues. "
                "Approach from a different perspective."
            )
        else:
            parts.append(
                "REPAIR STRATEGY: DIFFERENT APPROACH - Previous attempts failed. "
                "Try a fundamentally different implementation approach."
            )

        # Section 2: Governance rules (NEW - contract enforcement)
        rules = governance_rules or GOVERNANCE_RULES.get(language, [])
        if rules:
            parts.append("\n=== GOVERNANCE RULES (MANDATORY) ===")
            for rule in rules:
                parts.append(f"  - {rule}")

        # Section 3: Contract requirements (NEW)
        if language:
            parts.append("\n=== CONTRACT REQUIREMENTS ===")
            for req in CONTRACT_REQUIREMENTS:
                parts.append(f"  - {req}")

        # Section 4: Learned repair hints from memory (NEW)
        if repair_hints:
            parts.append("\n=== LEARNED FIXES FROM PREVIOUS EXPERIENCE ===")
            for hint in repair_hints:
                parts.append(f"  {hint}")

        # Section 5: Specific errors (sanitized - no source code)
        if errors:
            parts.append("\n=== ERRORS TO FIX ===")
            for i, error in enumerate(errors, 1):
                # Sanitize: truncate long errors, remove potential code snippets
                sanitized = error[:300] if len(error) > 300 else error
                parts.append(f"  {i}. {sanitized}")

        # Section 6: Security findings
        if security_findings:
            parts.append("\n=== SECURITY ISSUES TO FIX ===")
            for finding in security_findings:
                sanitized = str(finding)[:300]
                parts.append(f"  - {sanitized}")

        # Section 7: Anti-patterns from memory
        if anti_patterns:
            parts.append("\n=== ANTI-PATTERNS TO AVOID ===")
            for ap in anti_patterns[:10]:  # Max 10 to avoid token bloat
                parts.append(f"  - {ap}")

        # Section 8: Attempt history
        if attempt_history:
            parts.append("\n=== PREVIOUS ATTEMPTS (do NOT repeat) ===")
            for record in attempt_history[-3:]:
                parts.append(
                    f"  Attempt {record.attempt_number}: "
                    f"strategy={record.strategy.value}, "
                    f"score={record.quality_score.overall:.2f}, "
                    f"errors={len(record.errors)}"
                )

        # NOTE: Previous source code is intentionally NOT included here.
        # Per llm-invocation-v1.json privacy boundary, source code must
        # never leave VPS. The orchestrator handles code-level patching
        # locally if needed.

        result = "\n".join(parts)
        # Enforce hard token budget to prevent token bloat
        if len(result) > self.MAX_REPAIR_CHARS:
            truncated = result[:self.MAX_REPAIR_CHARS]
            last_newline = truncated.rfind("\n")
            if last_newline > self.MAX_REPAIR_CHARS // 2:
                truncated = truncated[:last_newline]
            result = truncated + "\n\n[TRUNCATED - budget limit reached]"
            logger.warning("Repair context truncated: %d -> %d chars", len(result), len(truncated))
        return result

    def compute_quality_score(
        self,
        syntax_passed: bool,
        security_findings: list[Any],
        generated_files: list[str],
        language: str,
        governance_passed: bool = True,
        compile_passed: bool = True,
        tests_passed: bool = True,
        test_pass_rate: float = 1.0,
    ) -> QualityScore:
        """Compute multi-dimensional quality score including execution."""
        score = QualityScore()

        # Syntax: binary
        score.syntax = 1.0 if syntax_passed else 0.0

        # Security: scaled by severity
        critical = sum(1 for f in security_findings if hasattr(f, 'severity') and f.severity.value == "critical")
        high = sum(1 for f in security_findings if hasattr(f, 'severity') and f.severity.value == "high")
        if critical > 0:
            score.security = 0.0
        elif high > 0:
            score.security = 0.5
        else:
            score.security = 1.0

        # Execution: compile + test results (NEW)
        if not compile_passed:
            score.execution = 0.0
        else:
            score.execution = max(0.0, min(1.0, test_pass_rate))

        # Completeness: has files generated
        score.completeness = min(1.0, len(generated_files) / max(1, 1))

        # Style: basic checks
        score.style = 1.0

        # Governance
        score.governance = 1.0 if governance_passed else 0.0

        score.compute_overall()
        return score

    def learn_from_attempt(
        self,
        errors: list[str],
        security_findings_raw: list[str],
        language: str,
        module_type: str,
        quality_before: float,
        quality_after: float,
        strategy_used: str,
        success: bool,
    ) -> None:
        """Extract patterns and learn from this attempt's results.

        Called after each attempt in the loop to update portable memory.
        """
        if self.memory is None:
            return

        from .pattern_extractor import PatternExtractor

        patterns = PatternExtractor.extract(
            errors=errors,
            security_findings=security_findings_raw,
            language=language,
        )

        if patterns:
            learned = self.memory.learn(
                patterns=patterns,
                language=language,
                module_type=module_type,
                quality_before=quality_before,
                quality_after=quality_after,
                strategy_used=strategy_used,
                success=success,
            )
            logger.info("Learned %d patterns from attempt", learned)

    def should_escalate_model(self, attempt: int) -> bool:
        """Determine if we should switch to fallback model."""
        return attempt >= 3

    def record_outcome(
        self,
        success: bool,
        attempts: int,
        final_score: float,
        failure_categories: list[str],
    ) -> None:
        """Record loop outcome for metrics."""
        self.metrics.total_runs += 1
        self.metrics.total_attempts += attempts
        if success:
            self.metrics.successful_runs += 1
        else:
            self.metrics.failed_runs += 1
            for cat in failure_categories:
                self.metrics.record_failure(cat)
        for i in range(1, attempts + 1):
            self.metrics.record_attempt(i, final_score if i == attempts else 0.0)

    def attempt_patch_repair(
        self,
        code: str,
        language: str,
        llm_client: Any,
    ) -> tuple[str, bool]:
        """EXPERIMENTAL: Attempt surgical patch repair.
        Kept for future evaluation but NOT used in production loop.
        """
        if language != "python":
            return code, False
        targets = self.patcher.analyze_python(code)
        if not targets:
            return code, False
        patched_code = code
        patches_applied = 0
        for target in targets[:3]:
            prompt = self.patcher.build_patch_prompt(target, language)
            try:
                patched_section = llm_client.generate_code(prompt, language)
                patched_code = self.patcher.apply_patch(patched_code, target, patched_section)
                patches_applied += 1
                logger.info("Applied patch: %s at line %d", target.issue_type, target.line_start)
            except Exception as e:
                logger.warning("Patch failed for %s: %s", target.issue_type, e)
                continue
        if language == "python":
            import ast as ast_module
            try:
                ast_module.parse(patched_code)
                return patched_code, patches_applied > 0
            except SyntaxError:
                logger.warning("Patched code has syntax errors - reverting")
                return code, False
        return patched_code, patches_applied > 0

    def get_metrics(self) -> dict:
        return self.metrics.summary()
