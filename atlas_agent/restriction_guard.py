"""Restriction Guard — 3-Layer Defense for CONSTITUTION.md §17.

Layer 1: Intent Classification — Is this a scaffold or implementation request?
Layer 2: Structural Validation — Does the output contain real business logic?
Layer 3: Audit Trail — Every decision logged for human review.

Design principles:
- No keyword substring matching (fragile, false positives)
- Template-based intent detection (deterministic)
- Output validation catches what input validation misses
- Every decision is auditable
"""

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class RequestIntent(Enum):
    """Classified intent of a code generation request."""
    SCAFFOLD = "scaffold"          # Structure only, no business logic
    IMPLEMENTATION = "implementation"  # Full implementation
    AMBIGUOUS = "ambiguous"        # Cannot determine — default to BLOCK


class RestrictionCategory(Enum):
    """§17 restricted categories."""
    HFT_CORE = "hft_core"
    EXECUTION_LOGIC = "execution_logic"
    RISK_SYSTEMS = "risk_systems"
    TRADING_STRATEGIES = "trading_strategies"


@dataclass(frozen=True)
class GuardDecision:
    """Immutable record of a restriction guard decision."""
    allowed: bool
    intent: RequestIntent
    category: Optional[RestrictionCategory]
    reason: str
    timestamp: float = field(default_factory=time.time)
    prompt_hash: str = ""
    layer: str = ""  # Which layer made the decision


# ============================================================
# Layer 1: Intent Classification
# ============================================================

# Scaffold indicators — must have AT LEAST 2 of these to classify as SCAFFOLD
SCAFFOLD_INDICATORS = [
    r'\bscaffold\b',
    r'\bstub\b',
    r'\btrait\s+definition\b',
    r'\bstruct\s+definition\b',
    r'\benum\s+definition\b',
    r'todo!\(\)',
    r'unimplemented!\(\)',
    r'\bno\s+implementation\b',
    r'\bwithout\s+implementation\b',
    r'\bdo\s+not\s+implement\b',
    r'\bforbidden\s+per\b',
    r'\bonly\s+(the\s+)?structure\b',
    r'\bonly\s+(the\s+)?definitions?\b',
    r'\bplaceholder\b',
]

# Implementation indicators — ANY of these means IMPLEMENTATION
IMPLEMENTATION_INDICATORS = [
    r'\bimplement\s+the\b',
    r'\bwrite\s+the\s+logic\b',
    r'\bbusiness\s+logic\s+for\b',
    r'\balgorithm\s+for\b',
    r'\bcalculate\s+the\b',
    r'\bfn\s+assess\s*\(',
    r'\bfn\s+execute\s*\(',
    r'\bfn\s+evaluate\s*\(',
    r'\bposition\s+sizing\s+logic\b',
    r'\brisk\s+assessment\s+logic\b',
    r'\border\s+routing\s+logic\b',
    r'\bsignal\s+generation\s+logic\b',
]

# Category detection patterns (word boundary aware)
CATEGORY_PATTERNS = {
    RestrictionCategory.HFT_CORE: [
        r'\bhigh[\s-]?frequency\b', r'\bhft\b', r'\bnanosecond\s*timing\b',
        r'\blatency[\s-]?critical\s*execution\b',
    ],
    RestrictionCategory.EXECUTION_LOGIC: [
        r'\border[\s_]*execution\b', r'\btrade[\s_]*execution\b',
        r'\bexecution[\s_]*engine\b', r'\border[\s_]*routing\b',
        r'\bexchange[\s_]*order\b', r'\bordermanager\b',
    ],
    RestrictionCategory.RISK_SYSTEMS: [
        r'\brisk[\s_]*engine\b', r'\brisk[\s_]*management\b',
        r'\bposition[\s_]*limit', r'\bexposure[\s_]*control\b',
        r'\bmargin[\s_]*calculation\b', r'\brisk[\s_]*assessment\b',
    ],
    RestrictionCategory.TRADING_STRATEGIES: [
        r'\btrading[\s_]*strateg', r'\bstrategy[\s_]*logic\b',
        r'\bsignal[\s_]*generation\b', r'\bbacktest[\s_]*engine\b',
        r'\balpha[\s_]*generation\b', r'\bstrategysignal\b',
    ],
}


def classify_intent(prompt: str) -> RequestIntent:
    """Layer 1: Classify whether request is scaffold or implementation.
    
    Uses regex with word boundaries — no substring false positives.
    Requires >=2 scaffold indicators AND 0 implementation indicators.
    """
    text = prompt.lower()
    
    scaffold_hits = sum(
        1 for pattern in SCAFFOLD_INDICATORS
        if re.search(pattern, text)
    )
    
    impl_hits = sum(
        1 for pattern in IMPLEMENTATION_INDICATORS
        if re.search(pattern, text)
    )
    
    if impl_hits > 0:
        return RequestIntent.IMPLEMENTATION
    
    if scaffold_hits >= 2:
        return RequestIntent.SCAFFOLD
    
    return RequestIntent.AMBIGUOUS


def detect_category(prompt: str) -> Optional[RestrictionCategory]:
    """Detect which §17 category a prompt falls into."""
    text = prompt.lower()
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return category
    return None


# ============================================================
# Layer 2: Structural Validation (post-generation)
# ============================================================

# Patterns that indicate REAL implementation (not scaffold)
IMPLEMENTATION_PATTERNS_RUST = [
    r'fn\s+\w+\s*\([^)]*\)\s*->\s*[^{]*\{[^}]{50,}',  # Function with substantial body
    r'(?:if|match|while|for)\s+.*\{.*(?:return|Err|Ok)',  # Control flow with returns
    r'\.(?:assess|execute|evaluate|calculate|compute)\s*\(',  # Business method calls
]

IMPLEMENTATION_PATTERNS_PYTHON = [
    r'def\s+\w+\s*\(self[^)]*\)[^:]*:\s*\n(?:\s+.+\n){5,}',  # Method with 5+ lines
    r'(?:if|elif|while|for)\s+.+:\s*\n\s+.*(?:return|raise)',  # Control flow
    r'\.(?:assess|execute|evaluate|calculate|compute)\s*\(',  # Business method calls
]

SCAFFOLD_PATTERNS_RUST = [
    r'todo!\(\)',
    r'unimplemented!\(\)',
    r'unreachable!\(\)',
    r'fn\s+\w+\s*\([^)]*\)\s*->\s*[^{]*\{\s*(?:todo|unimplemented)',
]

SCAFFOLD_PATTERNS_PYTHON = [
    r'raise\s+NotImplementedError',
    r'\.\.\.',  # Ellipsis placeholder
    r'pass\s*$',
]


def validate_output_structure(code: str, language: str) -> tuple[bool, str]:
    """Layer 2: Validate that generated code is actually a scaffold.
    
    Returns (is_valid_scaffold, reason).
    """
    if language == "rust":
        has_todo = any(re.search(p, code) for p in SCAFFOLD_PATTERNS_RUST)
        has_impl = any(re.search(p, code, re.DOTALL) for p in IMPLEMENTATION_PATTERNS_RUST)
    elif language == "python":
        has_todo = any(re.search(p, code, re.MULTILINE) for p in SCAFFOLD_PATTERNS_PYTHON)
        has_impl = any(re.search(p, code, re.DOTALL) for p in IMPLEMENTATION_PATTERNS_PYTHON)
    else:
        return True, "Non-restricted language"
    
    if has_todo and not has_impl:
        return True, "Valid scaffold: has stubs, no implementation"
    
    if has_impl and not has_todo:
        return False, "REJECTED: contains implementation without stubs"
    
    if has_impl and has_todo:
        return False, "REJECTED: mixed scaffold + implementation"
    
    return False, "REJECTED: no recognizable scaffold markers"


# ============================================================
# Layer 3: Main Guard Interface
# ============================================================

class RestrictionGuard:
    """3-layer restriction guard for CONSTITUTION.md §17."""
    
    def __init__(self) -> None:
        self._audit_log: list[GuardDecision] = []
    
    def check_request(self, prompt: str) -> GuardDecision:
        """Layer 1: Check if request should be allowed."""
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        
        # Step 1: Detect category
        category = detect_category(prompt)
        
        if category is None:
            decision = GuardDecision(
                allowed=True,
                intent=RequestIntent.SCAFFOLD,
                category=None,
                reason="No restricted category detected",
                prompt_hash=prompt_hash,
                layer="L1",
            )
            self._audit_log.append(decision)
            return decision
        
        # Step 2: Classify intent
        intent = classify_intent(prompt)
        
        if intent == RequestIntent.IMPLEMENTATION:
            decision = GuardDecision(
                allowed=False,
                intent=intent,
                category=category,
                reason=f"BLOCKED: implementation request for restricted category '{category.value}'",
                prompt_hash=prompt_hash,
                layer="L1",
            )
            self._audit_log.append(decision)
            logger.warning("§17 BLOCK: %s", decision.reason)
            return decision
        
        if intent == RequestIntent.AMBIGUOUS:
            decision = GuardDecision(
                allowed=False,
                intent=intent,
                category=category,
                reason=f"BLOCKED: ambiguous intent for restricted category '{category.value}' — use explicit SCAFFOLD markers",
                prompt_hash=prompt_hash,
                layer="L1",
            )
            self._audit_log.append(decision)
            logger.warning("§17 BLOCK (ambiguous): %s", decision.reason)
            return decision
        
        # Scaffold intent for restricted category — allow with warning
        decision = GuardDecision(
            allowed=True,
            intent=intent,
            category=category,
            reason=f"ALLOWED: scaffold-only for '{category.value}' — Layer 2 will validate output",
            prompt_hash=prompt_hash,
            layer="L1",
        )
        self._audit_log.append(decision)
        logger.info("§17 SCAFFOLD ALLOW: %s", decision.reason)
        return decision
    
    def validate_output(self, code: str, language: str, decision: GuardDecision) -> GuardDecision:
        """Layer 2: Validate generated output matches scaffold intent."""
        if decision.category is None:
            return decision  # Non-restricted, skip validation
        
        is_valid, reason = validate_output_structure(code, language)
        
        if not is_valid:
            output_decision = GuardDecision(
                allowed=False,
                intent=decision.intent,
                category=decision.category,
                reason=f"L2 REJECTED: {reason}",
                prompt_hash=decision.prompt_hash,
                layer="L2",
            )
            self._audit_log.append(output_decision)
            logger.error("§17 L2 BLOCK: %s", reason)
            return output_decision
        
        output_decision = GuardDecision(
            allowed=True,
            intent=decision.intent,
            category=decision.category,
            reason=f"L2 PASSED: {reason}",
            prompt_hash=decision.prompt_hash,
            layer="L2",
        )
        self._audit_log.append(output_decision)
        return output_decision
    
    def get_audit_trail(self) -> list[GuardDecision]:
        """Return full audit trail for human review."""
        return list(self._audit_log)
    
    def stats(self) -> dict:
        blocked = sum(1 for d in self._audit_log if not d.allowed)
        allowed = sum(1 for d in self._audit_log if d.allowed)
        scaffolds = sum(1 for d in self._audit_log if d.intent == RequestIntent.SCAFFOLD and d.category)
        return {
            "total_decisions": len(self._audit_log),
            "blocked": blocked,
            "allowed": allowed,
            "scaffolds_allowed": scaffolds,
        }
