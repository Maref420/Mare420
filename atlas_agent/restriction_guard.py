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

__all__ = ['RestrictionGuard', 'GuardDecision', 'RequestIntent', 'RestrictionCategory']


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
# Rules loaded from contract: contracts/schemas/ai/restriction-rules-v1.json
# NEVER define patterns inline. Single source of truth = JSON contract.
# ============================================================
import json
from pathlib import Path

_CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contracts" / "schemas" / "ai" / "restriction-rules-v1.json"

def _load_rules() -> dict:
    """Load §17 rules from JSON contract file."""
    try:
        with open(_CONTRACT_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("§17 contract not found at %s — using empty rules", _CONTRACT_PATH)
        return {"categories": {}, "intent_classification": {}}

_RULES = _load_rules()

SCAFFOLD_INDICATORS: list[str] = _RULES.get("intent_classification", {}).get("scaffold_indicators", [])
IMPLEMENTATION_INDICATORS: list[str] = _RULES.get("intent_classification", {}).get("implementation_indicators", [])

# Build CATEGORY_PATTERNS from contract, mapping string keys to RestrictionCategory enums
_CATEGORY_MAP = {
    "hft_core": RestrictionCategory.HFT_CORE,
    "execution_logic": RestrictionCategory.EXECUTION_LOGIC,
    "risk_systems": RestrictionCategory.RISK_SYSTEMS,
    "trading_strategies": RestrictionCategory.TRADING_STRATEGIES,
}

CATEGORY_PATTERNS: dict[RestrictionCategory, list[str]] = {}
for cat_key, cat_data in _RULES.get("categories", {}).items():
    enum_val = _CATEGORY_MAP.get(cat_key)
    if enum_val:
        CATEGORY_PATTERNS[enum_val] = cat_data.get("patterns", [])

logger.info("§17 rules loaded from contract: %d categories, %d scaffold indicators, %d impl indicators",
           len(CATEGORY_PATTERNS), len(SCAFFOLD_INDICATORS), len(IMPLEMENTATION_INDICATORS))


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