"""
Atlas AI Governance Prompt Builder v2.0.0
Single source of truth for LLM code generation prompts.
Every prompt MUST pass through this builder before reaching any LLM provider.
CONSTITUTION.md section 5: SpecCore MAY create specifications.
This module IS the specification-to-prompt translation layer.
Traceability (section 21): Every prompt is versioned and hashed.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROMPT_VERSION = "2.0.0"

LAYER_0_INVARIANTS = """
LAYER 0: NON-NEGOTIABLE HARD INVARIANTS (VIOLATION = INVALID OUTPUT)

I1  INSPECT REAL PATHS BEFORE DESIGNING. Never assume layout, ports, or secrets.
I2  ONE OWNER PER UNIT OF WORK. Python=intelligence, Rust=compute, Go=transfer.
    NEVER networking in Rust "because fast". NEVER ML in Go "because concurrent".
    NEVER gateways in Python "because convenient".
I3  CROSS-SERVICE ERRORS = ErrorEnvelope. VAL_/AUTH_/BIZ_=no retry.
    DEP_/RES_/NET_=retry. INT_=no retry+ALERT. Never leak panics across boundaries.
I4  RETRY ONLY WHEN retryable=true. Max 1+2 retries. Jittered backoff.
    Honor remaining parent deadline. Idempotency-Key for writes.
I5  DEADLINES PROPAGATE edge to leaf. Remaining time honored.
I6  NO SECRETS IN REPO. No stack traces to external clients.
I7  NO panic/unwrap (Rust), NO bare except (Python), NO ignored err (Go). EVER.
I8  TESTS PROVE THE BEHAVIOR. No test = no merge.
I9  COMPLETE FILES ONLY. No skeletons. No "rest omitted".
I10 NO PARALLEL PATHS. NO PACIFICATION. Fix root cause. Merge into governance.
"""

LAYER_1_RESTRICTIONS = """
LAYER 1: SECTION 17 EXTERNAL AI RESTRICTIONS (ABSOLUTE BLOCK)

PROHIBITED (RestrictionGuard will block regardless):
  HFT_CORE: high-frequency trading, nanosecond timing, latency-critical execution
  EXECUTION_LOGIC: order execution, trade execution, execution engine, order routing
  RISK_SYSTEMS: risk engine, risk management, position limit, exposure control
  TRADING_STRATEGIES: trading strategy, signal generation, backtest engine, alpha gen

If requirement touches ANY category: return "BLOCKED: section 17 restriction"
Do NOT attempt partial or workaround code.
"""

LAYER_2_PHILOSOPHY = """
LAYER 2: ENGINEERING PHILOSOPHY

Atlas AI = governance-first platform. Official flow:
  Requirement -> Architecture -> Specification -> Policy Validation
  -> Implementation Engine (YOU) -> Validation -> Human Approval -> Deployment

CORE PRINCIPLES:
  P1: ARCHITECTURE FIRST
  P2: SPEC BEFORE CODE
  P3: POLICY BEFORE GENERATION
  P4: SECURITY FIRST
  P5: MODULAR OWNERSHIP
  P6: NO PLACEHOLDERS
"""

LAYER_3_OPERATING_LOOP = """
LAYER 3: OPERATING LOOP - YOU ARE AT STEP E

Full loop: A)Context -> B)Ownership -> C)Contract -> D)Plan -> E)Implement(YOU) -> F)Verify
Steps A-D completed by governance layer before this prompt reaches you.
"""

LANGUAGE_RULES = {
    "python": """
LAYER 4: PYTHON ENGINE RULES (CONSTITUTION section 8)

OWNERSHIP: AI systems, ML, agents, orchestration, decisioning.
NOT YOUR JOB: Raw packet I/O (Go), CPU hot paths (Rust).

MUST: strict typing at boundaries, dependency control, validation before release.
IDIOMS: AppError domain exceptions, NO bare except, structlog, asyncio-aware.
FORBIDDEN: floats in financial calc (use Decimal), blocking I/O in async, global mutable state.

EXAMPLE:
    from __future__ import annotations
    from decimal import Decimal
    from typing import Any
    import structlog
    logger = structlog.get_logger(__name__)

    class AppError(Exception):
        def __init__(self, code: str, message: str, retryable: bool = False) -> None:
            self.code = code
            self.retryable = retryable
            super().__init__(message)

    def process(req_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not req_id:
            raise AppError("VAL_EMPTY_REQ_ID", "req_id must not be empty")
        logger.info("processing", req_id=req_id)
        return {"status": "processed", "req_id": req_id}
""",
    "rust": """
LAYER 4: RUST ENGINE RULES (CONSTITUTION section 7)

OWNERSHIP: Performance-critical compute, parsers, crypto, hot loops, safety-critical.
NOT YOUR JOB: Business decisions (Python), Gateway/routing (Go).

MUST: memory safety, overflow prevention, deterministic behavior, minimal overhead.
IDIOMS: thiserror, Result on request path, bounded channels, no hidden globals.
FORBIDDEN: unwrap()/expect() on request paths, unbounded Vec/String, business logic.

EXAMPLE:
    use thiserror::Error;

    #[derive(Error, Debug)]
    pub enum EngineError {
        #[error("validation failed: {0}")]
        Validation(String),
        #[error("compute timeout after {0}ms")]
        Timeout(u64),
        #[error("internal invariant broken: {0}")]
        Invariant(String),
    }

    pub fn compute(input: &[u8], deadline_ms: u64) -> Result<Vec<u8>, EngineError> {
        if input.is_empty() {
            return Err(EngineError::Validation("empty input".into()));
        }
        Ok(Vec::new())
    }
""",
    "go": """
LAYER 4: GO ENGINE RULES (Master Prompt section 2)

OWNERSHIP: HTTP/gRPC gateways, streaming, RPC fan-out, backpressure, workers, transport.
NOT YOUR JOB: ML/model inference (Python), CPU-bound compute (Rust).

MUST: context.Context on every RPC/IO, client timeouts, no goroutine leaks, backpressure.
IDIOMS: fmt.Errorf("%w", err), context propagation, structured logging with trace_id.
FORBIDDEN: ignored errors, goroutines without cancellation, external deps beyond stdlib.

EXAMPLE:
    package gateway

    import (
        "context"
        "fmt"
        "log/slog"
        "time"
    )

    type AppError struct {
        Code      string
        Message   string
        Retryable bool
        Cause     error
    }

    func (e *AppError) Error() string {
        if e.Cause != nil {
            return fmt.Sprintf("%s: %s: %v", e.Code, e.Message, e.Cause)
        }
        return fmt.Sprintf("%s: %s", e.Code, e.Message)
    }

    func (e *AppError) Unwrap() error { return e.Cause }

    func HandleRequest(ctx context.Context, reqID string) error {
        ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
        defer cancel()
        if reqID == "" {
            return &AppError{Code: "VAL_EMPTY_REQ_ID", Message: "req_id required"}
        }
        slog.InfoContext(ctx, "handling_request", "req_id", reqID)
        return nil
    }
""",
}

OWNERSHIP_RULES = {
    "gateway": "GATEWAY (Go): services/gateway/**. May import proto stubs only. First responder: invalid requests, auth, transport.",
    "agent": "AGENT (Python): intelligence/** or services/agent/**. May import proto stubs only. First responder: business decisions, model failures.",
    "engine": "ENGINE (Rust): core_engine/** or services/engine/**. May import proto stubs only. First responder: compute results.",
    "contract": "CONTRACT (Shared): contracts/** or proto/**. Schemas/docs only. NO business logic. Backward compatible.",
}

LAYER_6_CODING_STANDARD = """
LAYER 6: PRODUCTION CODING STANDARD

QUALITY BAR: complete types at boundaries, errors=values with stable codes,
no swallowed errors, context/deadline propagates, graceful shutdown,
structured logs (service, trace_id, span_id, code, duration_ms),
health liveness vs readiness, tests cover changed behavior.

FORBIDDEN: giant utils, premature abstractions, new deps for trivial functions,
unused imports, dead code, duplicated logic, meaningless comments.

DETERMINISTIC EXECUTION (section 12):
  PROHIBITED: Market Data -> AI Inference -> Execution
  APPROVED: Market Data -> Deterministic Processing -> Risk Validation -> Execution

VALIDATION (section 18): architecture + policy + security + schema + testing.
TRACEABILITY (section 21): spec_id, engine_id, owner_id, policy_version, timestamp.
"""

LAYER_7_CONTRACT_TEMPLATE = """
LAYER 7: ACTIVE CONTRACT SCHEMAS

{schemas_content}

ErrorEnvelope (ALL cross-service failures):
  trace_id, span_id, service, code, retryable, http_status,
  message (safe), details, cause_chain, timestamp_ms

Retry: retryable=false -> NO RETRY. retryable=true -> max 1+2, jittered backoff,
       honor parent deadline, Idempotency-Key for writes.
"""

LAYER_8_PRE_CHANGE_GATES = """
LAYER 8: PRE-CHANGE GATES (VERIFIED BEFORE THIS PROMPT)

  [x] Language matches Matrix B (polyglot routing)
  [x] Policy reviewed in governance/policies/
  [x] Contract identified in contracts/schemas/
  [x] Production-grade test prepared
  [x] Governance registration location identified (ADR)
  [x] README documentation structure confirmed

Pre-change commands executed:
  [x] bash scripts/inspect-target.sh <target>
  [x] make check-parallel-paths
  [x] make validate-<module>
"""

LAYER_9_GOVERNANCE_PROTOCOL = """
LAYER 9: GOVERNANCE-FIRST CHANGE PROTOCOL

Your output MUST:
  1. Comply with existing governance (MERGE, never replace)
  2. Be production-grade (no quick fixes, no pacification)
  3. Be registered in governance (ADR in docs/decisions/)
  4. Be reflected in contract schemas (contracts/schemas/)
  5. Be documented in module README (data flow + sharing capability)

NO PARALLEL PATHS. NO PACIFICATION. FIX ROOT CAUSE.
"""

LAYER_10_TASK_TEMPLATE = """
LAYER 10: TASK SPECIFICATION

{task_specification}
"""

LAYER_11_OUTPUT_REQUIREMENTS = """
LAYER 11: OUTPUT REQUIREMENTS

FORMAT:
  - Provide ONLY complete, runnable source code
  - NO markdown fences around the code
  - NO explanations outside the code
  - NO "rest omitted" or skeleton code
  - Include ALL imports, types, error handling
  - Match existing project style exactly

CRITICAL FOR 0G MODEL:
  - Put reasoning in thinking block (system handles it)
  - Put ONLY final code in text response
  - Do NOT include code inside thinking blocks
  - Text response must be parseable as pure source code

POST-GENERATION VALIDATION (automated):
  1. Syntax validation (AST/build check)
  2. Schema compliance
  3. Section 17 restriction scan
  4. Security analysis
  5. Contract parity verification
  6. Production-grade tests

If validation fails, you receive structured repair context.
Fix ROOT CAUSE. Do not work around. Do not pacify.
"""

ATLAS_GOVERNANCE_PROMPT_TEMPLATE = """
ATLAS AI CODE GENERATION - GOVERNANCE PROMPT v{version}
Authority: CONSTITUTION.md v1.2 + MASTER_PROMPT_FULL.md
Prompt Hash: {prompt_hash}
Timestamp: {timestamp}

You are the Atlas AI Code Generator under strict governance.
Every line you produce is subject to CONSTITUTION v1.2.
You do not vibe-code. You do not invent parallel architectures.
You do not cross language boundaries without an explicit contract.
{layer_0}
{layer_1}
{layer_2}
{layer_3}
{layer_4}
{layer_5}
{layer_6}
{layer_7}
{layer_8}
{layer_9}
{layer_10}
{layer_11}

END OF GOVERNANCE PROMPT - ALL LAYERS MANDATORY - VIOLATION = REJECT
""".strip()


def _load_contract_schemas(module_name: str, language: str) -> str:
    schema_dir = Path("contracts/schemas")
    if not schema_dir.exists():
        return "No contract schema directory found."
    relevant_dirs = []
    ml = module_name.lower()
    if any(k in ml for k in ("memory", "forget", "retrieve", "store")):
        relevant_dirs.append("memory")
    if any(k in ml for k in ("risk", "kill", "circuit")):
        relevant_dirs.extend(["risk", "execution"])
    if any(k in ml for k in ("audit", "log", "trace")):
        relevant_dirs.append("audit")
    if any(k in ml for k in ("event", "signal", "market")):
        relevant_dirs.append("events")
    if any(k in ml for k in ("deploy", "approval", "coding", "artifact")):
        relevant_dirs.append("coding-loop")
    if any(k in ml for k in ("ai", "llm", "restrict", "generat")):
        relevant_dirs.append("ai")
    if any(k in ml for k in ("ffi", "sdk", "module", "registry")):
        relevant_dirs.append("sdk")
    if any(k in ml for k in ("security", "finding")):
        relevant_dirs.append("security")
    if any(k in ml for k in ("exchange", "connector")):
        relevant_dirs.append("exchange")
    if any(k in ml for k in ("strategy", "signal")):
        relevant_dirs.append("strategy")
    if "audit" not in relevant_dirs:
        relevant_dirs.append("audit")
    schemas_text = []
    for subdir in relevant_dirs:
        dir_path = schema_dir / subdir
        if not dir_path.exists():
            continue
        for sf in sorted(dir_path.glob("*.json")):
            try:
                with open(sf) as f:
                    schema = json.load(f)
                title = schema.get("title", sf.name)
                desc = schema.get("description", "")[:200]
                schemas_text.append(f"--- {sf.relative_to(schema_dir)} ---\nTitle: {title}\nDesc: {desc}")
            except (json.JSONDecodeError, OSError):
                continue
    if not schemas_text:
        return "No relevant schemas found for this module."
    combined = "\n".join(schemas_text)
    if len(combined) > 2000:
        combined = combined[:2000] + "\n... (truncated for token budget)"
    return combined


def _detect_ownership_type(module_name: str, language: str) -> str:
    nl = module_name.lower()
    if any(k in nl for k in ("gateway", "router", "proxy", "api")):
        return "gateway"
    if any(k in nl for k in ("engine", "core", "compute", "parser")):
        return "engine"
    if any(k in nl for k in ("contract", "schema", "proto")):
        return "contract"
    if language.lower() == "go":
        return "gateway"
    if language.lower() == "rust":
        return "engine"
    return "agent"


def build_governance_prompt(
    requirement: str,
    language: str,
    module_name: str,
    project_name: str,
    architecture: str,
    modules: list[dict],
    memory_context: Optional[str] = None,
    repair_context: Optional[str] = None,
) -> tuple[str, str]:
    lang_rules = LANGUAGE_RULES.get(language.lower(), LANGUAGE_RULES["python"])
    ownership_type = _detect_ownership_type(module_name, language)
    ownership_rules = OWNERSHIP_RULES.get(ownership_type, OWNERSHIP_RULES["agent"])
    schemas_content = _load_contract_schemas(module_name, language)
    task_parts = [
        f"Language: {language}",
        f"Module: {module_name}",
        f"Project: {project_name}",
        f"Requirement: {requirement}",
        f"Architecture: {architecture}",
        f"All modules: {chr(44).join(m.get(chr(110)+chr(97)+chr(109)+chr(101), chr(0)) for m in modules)}",
    ]
    if memory_context:
        task_parts.append(f"\nMemory Context:\n{memory_context}")
    if repair_context:
        task_parts.append(
            f"\nREPAIR CONTEXT (PREVIOUS ATTEMPT FAILED):\n"
            f"{repair_context}\n"
            f"Fix ROOT CAUSE. Do not work around. Do not pacify."
        )
    task_spec = "\n".join(task_parts)
    ts = datetime.now(timezone.utc).isoformat()
    raw = ATLAS_GOVERNANCE_PROMPT_TEMPLATE.format(
        version=PROMPT_VERSION, prompt_hash="PENDING", timestamp=ts,
        layer_0=LAYER_0_INVARIANTS, layer_1=LAYER_1_RESTRICTIONS,
        layer_2=LAYER_2_PHILOSOPHY, layer_3=LAYER_3_OPERATING_LOOP,
        layer_4=lang_rules, layer_5=ownership_rules,
        layer_6=LAYER_6_CODING_STANDARD,
        layer_7=LAYER_7_CONTRACT_TEMPLATE.format(schemas_content=schemas_content),
        layer_8=LAYER_8_PRE_CHANGE_GATES, layer_9=LAYER_9_GOVERNANCE_PROTOCOL,
        layer_10=LAYER_10_TASK_TEMPLATE.format(task_specification=task_spec),
        layer_11=LAYER_11_OUTPUT_REQUIREMENTS,
    )
    ph = hashlib.sha256(raw.encode()).hexdigest()[:16]
    final = ATLAS_GOVERNANCE_PROMPT_TEMPLATE.format(
        version=PROMPT_VERSION, prompt_hash=ph, timestamp=ts,
        layer_0=LAYER_0_INVARIANTS, layer_1=LAYER_1_RESTRICTIONS,
        layer_2=LAYER_2_PHILOSOPHY, layer_3=LAYER_3_OPERATING_LOOP,
        layer_4=lang_rules, layer_5=ownership_rules,
        layer_6=LAYER_6_CODING_STANDARD,
        layer_7=LAYER_7_CONTRACT_TEMPLATE.format(schemas_content=schemas_content),
        layer_8=LAYER_8_PRE_CHANGE_GATES, layer_9=LAYER_9_GOVERNANCE_PROTOCOL,
        layer_10=LAYER_10_TASK_TEMPLATE.format(task_specification=task_spec),
        layer_11=LAYER_11_OUTPUT_REQUIREMENTS,
    )
    return final, ph


def build_structured_repair_context(
    error_classification: str,
    failing_boundary: str,
    error_messages: list[str],
    previous_code_hash: Optional[str] = None,
    attempt_number: int = 1,
) -> str:
    parts = [
        f"Classification: {error_classification}",
        f"Failing boundary: {failing_boundary}",
        f"Attempt: {attempt_number}",
    ]
    if previous_code_hash:
        parts.append(f"Previous code hash: {previous_code_hash}")
    parts.append("")
    parts.append("Errors:")
    for i, msg in enumerate(error_messages, 1):
        parts.append(f"  {i}. {msg}")
    parts.append("")
    parts.append("Diagnosis:")
    for msg in error_messages:
        mu = msg.upper()
        if any(c in mu for c in ("VAL_", "AUTH_", "BIZ_")):
            parts.append("  -> Fix caller or contract. Do NOT retry.")
        elif any(c in mu for c in ("NET_", "DEP_", "RES_")):
            parts.append("  -> Check deadline, peer health, retry budget.")
        elif "INT_" in mu:
            parts.append("  -> Invariant bug in producing service.")
    return "\n".join(parts)
