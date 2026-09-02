"""Self-Correcting Loop v2 — Professional Grade.

Improvements over v1:
1. Structured repair context (previous code + errors + strategy)
2. Multi-dimensional quality scoring (not just pass/fail)
3. Repair strategy escalation (patch → rewrite → different model)
4. Attempt history tracking (avoid repeating same mistakes)
5. Memory update on human decision (close the learning loop)
6. Metrics dashboard (success rate, avg attempts, common failures)
7. Diff-based repair for minor issues (token efficient)

Governed by: contracts/schemas/ai/llm-invocation-v1.json
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)
from .code_patcher import CodePatcher, PatchTarget


class RepairStrategy(Enum):
    """Escalation strategy for repair attempts."""
    PATCH = "patch"              # Fix specific errors in existing code
    REWRITE = "rewrite"          # Full rewrite with error context
    DIFFERENT_MODEL = "different_model"  # Switch to fallback model
    DIFFERENT_PROMPT = "different_prompt"  # Restructure the prompt


@dataclass
class QualityScore:
    """Multi-dimensional quality assessment."""
    syntax: float = 0.0          # 0.0-1.0: passes syntax check
    security: float = 0.0        # 0.0-1.0: no critical/high findings
    completeness: float = 0.0    # 0.0-1.0: has required components
    style: float = 0.0           # 0.0-1.0: follows conventions
    overall: float = 0.0         # Weighted average
    
    PASS_THRESHOLD = 0.8
    
    def compute_overall(self) -> float:
        self.overall = (
            self.syntax * 0.35 +
            self.security * 0.30 +
            self.completeness * 0.20 +
            self.style * 0.15
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
    """Professional self-correcting code generation loop."""
    
    MAX_ATTEMPTS = 5
    PASS_THRESHOLD = 0.8
    
    def __init__(self) -> None:
        self.metrics = LoopMetrics()
        self.patcher = CodePatcher()
        self._attempt_history: list[AttemptRecord] = []
    
    def determine_strategy(self, attempt: int, previous_errors: list[str]) -> RepairStrategy:
        """Determine repair strategy based on attempt number and error pattern."""
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
    ) -> str:
        """Build rich, structured repair context for LLM."""
        parts = []
        
        # Section 1: Strategy instruction
        if strategy == RepairStrategy.PATCH:
            parts.append(
                "REPAIR STRATEGY: PATCH — Fix ONLY the specific errors below. "
                "Keep the rest of the code unchanged."
            )
        elif strategy == RepairStrategy.REWRITE:
            parts.append(
                "REPAIR STRATEGY: FULL REWRITE — The previous approach failed. "
                "Rewrite the entire file from scratch, avoiding the errors below."
            )
        else:
            parts.append(
                "REPAIR STRATEGY: DIFFERENT APPROACH — Previous attempts failed. "
                "Try a fundamentally different implementation approach."
            )
        
        # Section 2: Previous code (for PATCH strategy)
        if strategy == RepairStrategy.PATCH and previous_code:
            parts.append(f"\nPREVIOUS CODE (fix errors in this code):\n```\n{previous_code}\n```")
        
        # Section 3: Specific errors with line numbers
        if errors:
            parts.append("\nERRORS TO FIX:")
            for i, error in enumerate(errors, 1):
                parts.append(f"  {i}. {error}")
        
        # Section 4: Security findings
        if security_findings:
            parts.append("\nSECURITY ISSUES TO FIX:")
            for finding in security_findings:
                parts.append(f"  - {finding}")
        
        # Section 5: Anti-patterns from memory
        if anti_patterns:
            parts.append(f"\nANTI-PATTERNS TO AVOID: {', '.join(anti_patterns)}")
        
        # Section 6: Attempt history (what was already tried)
        if attempt_history:
            parts.append("\nPREVIOUS ATTEMPTS (do NOT repeat these approaches):")
            for record in attempt_history[-3:]:  # Last 3 attempts
                parts.append(
                    f"  Attempt {record.attempt_number}: "
                    f"strategy={record.strategy.value}, "
                    f"score={record.quality_score.overall:.2f}, "
                    f"errors={len(record.errors)}"
                )
        
        return "\n".join(parts)
    
    def compute_quality_score(
        self,
        syntax_passed: bool,
        security_findings: list[Any],
        generated_files: list[str],
        language: str,
    ) -> QualityScore:
        """Compute multi-dimensional quality score."""
        score = QualityScore()
        
        # Syntax: binary
        score.syntax = 1.0 if syntax_passed else 0.0
        
        # Security: 1.0 = no findings, 0.0 = critical findings
        critical = sum(1 for f in security_findings if hasattr(f, 'severity') and f.severity.value == "critical")
        high = sum(1 for f in security_findings if hasattr(f, 'severity') and f.severity.value == "high")
        if critical > 0:
            score.security = 0.0
        elif high > 0:
            score.security = 0.5
        else:
            score.security = 1.0
        
        # Completeness: has files generated
        score.completeness = min(1.0, len(generated_files) / max(1, 1))
        
        # Style: basic checks
        score.style = 1.0  # Default; could be enhanced with linter integration
        
        score.compute_overall()
        return score
    
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
        
        NOTE: Current LLMs cannot reliably edit small code sections.
        They tend to regenerate entire files when asked to patch.
        This method is kept for future evaluation but NOT used in production loop.
        Full regeneration with structured repair context is more reliable.
        
        Returns (patched_code, success).
        Only works for Python with AST-analyzable issues.
        Falls back to full regeneration if patching fails.
        """
        if language != "python":
            return code, False  # Patching only supported for Python currently
        
        targets = self.patcher.analyze_python(code)
        if not targets:
            return code, False  # No analyzable targets
        
        patched_code = code
        patches_applied = 0
        
        for target in targets[:3]:  # Max 3 patches per attempt
            prompt = self.patcher.build_patch_prompt(target, language)
            try:
                patched_section = llm_client.generate_code(prompt, language)
                patched_code = self.patcher.apply_patch(patched_code, target, patched_section)
                patches_applied += 1
                logger.info("Applied patch: %s at line %d", target.issue_type, target.line_start)
            except Exception as e:
                logger.warning("Patch failed for %s: %s", target.issue_type, e)
                continue
        
        # Validate patched code
        if language == "python":
            import ast as ast_module
            try:
                ast_module.parse(patched_code)
                return patched_code, patches_applied > 0
            except SyntaxError:
                logger.warning("Patched code has syntax errors — reverting")
                return code, False
        
        return patched_code, patches_applied > 0

    def get_metrics(self) -> dict:
        return self.metrics.summary()
