"""Orchestrator for ATLAS AI Agent - v2 with Portable Memory and Governance-Aware Loop.

Coordinates the workflow between Governance, Generator, Validator,
and Self-Correcting Loop with intelligent learning.

Governed by:
  - contracts/schemas/ai/llm-invocation-v1.json
  - contracts/schemas/ai/portable-memory-v1.json
  - CONSTITUTION.md section 17
"""
import logging
import os
import pathlib
import time

logger = logging.getLogger(__name__)

__all__ = ['Orchestrator']

from .deployment import DeploymentEngine
from .generator import GeneratorEngine
from .governance import GovernanceEngine, PolicyEnforcer
from .self_correcting_loop import LearningMemory, PortableMemory
from .models import ApprovalStatus, Artifact, Requirement, SecurityLevel, Specification
from .self_correcting_loop import QualityScore, SelfCorrectingLoop
from .validator import ValidatorEngine
from .analysis import RootCauseAnalyzer, AdversarialReviewer
from .delta_repair import DeltaRepairEngine


class Orchestrator:
    """Main orchestrator for the code generation pipeline.

    Integrates portable memory and governance-aware self-correcting loop.
    Learns from every attempt and enforces project contracts.
    """

    def __init__(self) -> None:
        self.governance = GovernanceEngine()
        self.policy_enforcer = PolicyEnforcer()
        self.deployer = DeploymentEngine(governance_engine=self.governance)
        self.generator = GeneratorEngine()
        self.validator = ValidatorEngine()
        self.memory = LearningMemory()
        self.portable_memory = PortableMemory()
        # Migrate legacy LearningMemory data into PortableMemory (Fix 5: drift)
        if self.memory.experiences and not self.portable_memory._experiences:
            migrated = self.portable_memory.migrate_from_legacy(self.memory)
            logger.info("Migrated %d legacy experiences to portable memory", migrated)
        self.loop = SelfCorrectingLoop(
            portable_memory=self.portable_memory,
            governance_engine=self.governance,
        )

    def run_pipeline(
        self, requirement: Requirement, architecture: str, modules: list[str]
    ) -> Artifact:
        """Execute the full code generation pipeline with learning."""
        self.governance.log_audit(
            "pipeline_start", "orchestrator",
            {"requirement": requirement.model_dump_json()},
        )

        # 1. Create Specification
        spec = Specification(
            requirement=requirement,
            architecture=architecture,
            modules=[{"name": m} for m in modules],
            dependencies=[],
        )

        # 2. Validate Specification
        if not self.governance.validate_specification(spec):
            self.governance.log_audit(
                "pipeline_failed", "orchestrator",
                error="Specification validation failed",
            )
            raise ValueError("Specification validation failed")

        # 3. Generate, validate, and repair code (Self-Correcting Loop v3)
        max_attempts = self.loop.MAX_ATTEMPTS
        repair_context = None
        artifact = None
        attempt_history = []
        lang = requirement.language.value
        quality = QualityScore()
        previous_quality = 0.0

        for attempt in range(1, max_attempts + 1):
            # Determine strategy using memory-optimized selection
            strategy = self.loop.determine_strategy(
                attempt, [], language=lang,
            )

            # Escalate to fallback model at attempt 3+
            original_model = self.generator.llm.model
            if self.loop.should_escalate_model(attempt):
                self.generator.llm.model = self.generator.llm.fallback_model

            t0 = time.time()
            generated_files = self.generator.generate_project(
                spec,
                requirement.target_folder,
                repair_context=repair_context,
            )
            latency = time.time() - t0

            # Restore primary model
            self.generator.llm.model = original_model

            artifact = Artifact(
                requirement=requirement,
                specification=spec,
                generated_files=generated_files,
            )

            # 4. Validate Generated Code
            source_extensions = {".py", ".rs", ".go"}
            source_files = [
                fp for fp in generated_files
                if any(fp.endswith(ext) for ext in source_extensions)
            ]
            all_syntax_passed = True

            if lang == "go":
                syntax_result = self.validator.check_syntax(
                    requirement.target_folder, lang,
                )
                artifact.test_results.append(syntax_result)
                if not syntax_result.passed:
                    all_syntax_passed = False
                for rel_path in source_files:
                    abs_path = os.path.join(requirement.target_folder, rel_path)
                    security_findings = self.validator.run_security_scan(
                        abs_path, lang, base_dir=requirement.target_folder,
                    )
                    artifact.security_findings.extend(security_findings)
            else:
                for rel_path in source_files:
                    abs_path = os.path.join(requirement.target_folder, rel_path)
                    syntax_result = self.validator.check_syntax(abs_path, lang)
                    artifact.test_results.append(syntax_result)
                    if not syntax_result.passed:
                        all_syntax_passed = False
                    security_findings = self.validator.run_security_scan(
                        abs_path, lang, base_dir=requirement.target_folder,
                    )
                    artifact.security_findings.extend(security_findings)

            # Check governance compliance
            governance_passed = self.governance.validate_artifact(artifact)

            # Check enforceable knowledge policies (reads rules from portable memory)
            artifact_files = {}
            for fp in artifact.generated_files:
                try:
                    base_dir = pathlib.Path(requirement.target_folder) if isinstance(requirement.target_folder, str) else requirement.target_folder
                    full_path = base_dir / fp if not str(fp).startswith("/") else pathlib.Path(fp)
                    if full_path.exists():
                        artifact_files[fp] = full_path.read_text(encoding="utf-8", errors="replace")
                except (OSError, ValueError):
                    pass
            policy_result = self.policy_enforcer.enforce(
                files=artifact_files, language=lang,
                knowledge=self.portable_memory._knowledge,
            )
            if not policy_result.passed:
                governance_passed = False
                policy_hints = self.policy_enforcer.format_violations_for_repair(policy_result)
                for hint in policy_hints[:5]:
                    repair_hints.append(hint)
                logger.warning("Policy enforcement failed: %d blocking violations",
                             len(policy_result.blocking_violations))

            # Execution feedback: compile check per file (FIXED)
            compile_errors = []
            compile_passed = True
            for _fp in artifact.generated_files:
                _abs = os.path.join(requirement.target_folder, _fp)
                if not os.path.isfile(_abs):
                    continue
                _cr = self.validator.compile_check(_abs, lang)
                if not _cr.passed:
                    compile_passed = False
                    compile_errors.extend(_cr.errors)
                    artifact.test_results.append(_cr)
            if not compile_passed:
                logger.warning("Compile check failed: %s", compile_errors[:3])

            test_results = []
            test_pass_rate = 1.0
            if compile_passed:
                test_results = self.validator.run_tests(
                    requirement.target_folder, lang,
                )
                for tr in test_results:
                    artifact.test_results.append(tr)
                    if hasattr(tr, "_pass_rate"):
                        test_pass_rate = tr._pass_rate
                tests_all_passed = all(tr.passed for tr in test_results) if test_results else True
            else:
                tests_all_passed = False

            # Compute multi-dimensional quality score (including execution)
            quality = self.loop.compute_quality_score(
                syntax_passed=all_syntax_passed,
                security_findings=artifact.security_findings,
                generated_files=generated_files,
                language=lang,
                governance_passed=governance_passed,
                compile_passed=compile_passed,
                tests_passed=tests_all_passed,
                test_pass_rate=test_pass_rate,
            )

            # Collect errors for attempt record (including compile+test)
            failed_results = [r for r in artifact.test_results if not r.passed]
            test_errors = [e for r in failed_results for e in r.errors if e]
            # Deduplicate and limit errors to prevent token bloat
            seen_errors = set()
            unique_errors = []
            for err in test_errors:
                normalized = err.strip()[:200]
                if normalized and normalized not in seen_errors:
                    seen_errors.add(normalized)
                    unique_errors.append(normalized)
            test_errors = unique_errors[:20]  # Max 20 unique errors
            security_errors = [
                f"[{f.severity.value.upper()}] {f.category}: {f.message} -> {f.suggestion}"
                for f in artifact.security_findings
                if f.severity in (SecurityLevel.CRITICAL, SecurityLevel.HIGH)
            ]

            # Record attempt in history
            from atlas_agent.self_correcting_loop import AttemptRecord

            code_len = 0
            for sf in source_files:
                fp = os.path.join(requirement.target_folder, sf)
                if os.path.exists(fp):
                    with open(fp) as fh:
                        code_len += len(fh.read())

            attempt_record = AttemptRecord(
                attempt_number=attempt,
                strategy=strategy,
                model_used=self.generator.llm.model,
                prompt_hash="",
                quality_score=quality,
                errors=test_errors,
                security_findings=security_errors,
                code_length=code_len,
                latency_seconds=latency,
            )
            attempt_history.append(attempt_record)

            logger.info(
                "Attempt %d/%d: score=%.2f strategy=%s errors=%d security=%d gov=%s latency=%.1fs",
                attempt, max_attempts, quality.overall, strategy.value,
                len(test_errors), len(security_errors),
                "pass" if governance_passed else "fail", latency,
            )

            # LEARN from this attempt (NEW - portable memory integration)
            module_type = modules[0] if modules else "unknown"
            self.loop.learn_from_attempt(
                errors=test_errors,
                security_findings_raw=security_errors,
                language=lang,
                module_type=module_type,
                quality_before=previous_quality,
                quality_after=quality.overall,
                strategy_used=strategy.value,
                success=quality.passed and governance_passed,
            )
            previous_quality = quality.overall

            # 5. Check if passed (quality threshold + governance)
            if quality.passed and governance_passed:
                self.loop.record_outcome(True, attempt, quality.overall, [])
                self.governance.log_audit("pipeline_success", "orchestrator", {
                    "attempts": attempt,
                    "score": quality.overall,
                    "strategy": strategy.value,
                    "loop_metrics": self.loop.get_metrics(),
                    "memory_stats": self.portable_memory.stats(),
                })
                break

            # Build governance-aware repair context for next attempt
            from atlas_agent.self_correcting_loop.pattern_extractor import PatternExtractor
            error_categories = PatternExtractor.extract_categories(test_errors)

            # PILLAR 1: Root Cause Analysis on failures
            rca_report = None
            rca_context = ""
            if test_errors:
                rca_report = RootCauseAnalyzer.analyze_local(test_errors, lang)
                rca_context = rca_report.to_repair_context()
                logger.info("RCA: %d findings, strategy=%s",
                           len(rca_report.findings), rca_report.recommended_strategy)

            # PILLAR 3: Adversarial pre-validation review
            adversarial_findings = []
            try:
                adversarial_findings = AdversarialReviewer.review(
                    language=lang,
                    module_type=modules[0] if modules else "unknown",
                    description=requirement.description[:500],
                    compile_errors=test_errors,
                    llm_client=self.generator.llm,
                )
            except Exception as e:
                logger.warning("Adversarial review skipped: %s", e)

            # Combine all errors for repair context
            enable_adversarial = os.environ.get("ATLAS_ENABLE_ADVERSARIAL", "0") == "1"

            # SAFE PHASED INJECTION:
            # Phase A: Always start with ONLY compile/test errors
            # Phase B: Only after compile passes, optionally add adversarial
            # RCA is metadata, injected separately via repair_hints NOT errors
            combined_errors = list(test_errors)

            has_compile_failures = any(
                not r.passed for r in artifact.test_results
                if getattr(r, "test_name", "") == "compile_check"
            )

            # Adversarial findings: ONLY when compile passes AND env enables it
            if enable_adversarial and not has_compile_failures and adversarial_findings:
                safe_adv = adversarial_findings[:3]
                combined_errors.extend(safe_adv)
                logger.info("Hardening phase: %d adversarial findings injected", len(safe_adv))
            elif adversarial_findings and has_compile_failures:
                logger.debug("Skipping adversarial: compile still failing (%d errors)", len(test_errors))

            # RCA will be injected into repair_hints after it is defined below

            # Get anti-patterns from portable memory
            anti_patterns = self.portable_memory.get_anti_pattern_descriptions(lang)
            if not anti_patterns:
                anti_patterns = list(self.memory.get_anti_patterns())

            # Get learned repair hints from portable memory
            repair_hints = self.portable_memory.get_repair_hints(lang, error_categories)

            # Inject RCA as hint (not error) to guide repair without prompt bloat
            if rca_context:
                repair_hints.insert(0, rca_context[:500])

            # Inject governance knowledge context (privacy, standards, LLM rules)
            # Phase-aware: only rules relevant to current phase + language
            knowledge_rules = self.portable_memory.get_knowledge_context(
                language=lang, module_type=requirement.module_type if hasattr(requirement, 'module_type') else "*",
                phase="repair", limit=8,
            )
            for rule in knowledge_rules[:5]:
                repair_hints.append(f"[GOVERNANCE] {rule[:200]}")

            # Use RCA-recommended strategy if available, otherwise use memory
            if rca_report and rca_report.recommended_strategy in ("patch", "rewrite", "different_approach"):
                from atlas_agent.self_correcting_loop import RepairStrategy
                try:
                    next_strategy = RepairStrategy(rca_report.recommended_strategy)
                except ValueError:
                    next_strategy = self.loop.determine_strategy(attempt + 1, test_errors, language=lang)
            else:
                next_strategy = self.loop.determine_strategy(attempt + 1, test_errors, language=lang)

            # PILLAR 2: Attempt Delta Repair before full regeneration
            enable_delta = os.environ.get("ATLAS_ENABLE_DELTA_REPAIR", "1") == "1"
            delta_applied = False
            if enable_delta and test_errors and generated_files:
                for gf in generated_files:
                    if not gf.endswith((".rs", ".go", ".py")):
                        continue
                    gf_path = os.path.join(requirement.target_folder, gf)
                    if not os.path.exists(gf_path):
                        continue
                    rca_text = rca_report.to_repair_context() if rca_report else ""
                    patch = DeltaRepairEngine.attempt_delta_repair(
                        file_path=gf_path,
                        errors=test_errors,
                        language=lang,
                        rca_context=rca_text,
                        llm_client=self.generator.llm,
                    )
                    if patch and patch.confidence >= 0.5:
                        applied = DeltaRepairEngine.apply_patch(patch)
                        if applied:
                            delta_applied = True
                            logger.info("Delta repair applied to %s", gf)
                            break  # One file at a time

            # If delta repair succeeded, re-validate instead of regenerating
            if delta_applied:
                logger.info("Re-validating after delta repair...")
                # Re-run compile check
                re_compile = self.validator.compile_check(requirement.target_folder, lang)
                if re_compile.passed:
                    re_tests = self.validator.run_tests(requirement.target_folder, lang)
                    all_pass = all(t.passed for t in re_tests) if re_tests else True
                    if all_pass:
                        logger.info("Delta repair SUCCESS - all checks pass")
                        artifact.status = "deployed"
                        artifact.test_results.append(re_compile)
                        artifact.test_results.extend(re_tests)
                        # Learn from success
                        self.portable_memory.learn_from_attempt(
                            requirement=requirement,
                            strategy=next_strategy.value if hasattr(next_strategy, 'value') else str(next_strategy),
                            quality_score=quality.overall,
                            errors=[],
                            security_findings=artifact.security_findings,
                            governance_passed=True,
                            language=lang,
                        )
                        return artifact
                    else:
                        logger.info("Delta repair: tests still failing, falling back to regeneration")
                else:
                    logger.info("Delta repair: compile still failing, falling back to regeneration")

            # Build repair context WITHOUT source code (privacy-safe)
            repair_context = self.loop.build_structured_repair_context(
                previous_code="",
                errors=combined_errors,
                security_findings=security_errors,
                anti_patterns=anti_patterns,
                attempt_history=attempt_history,
                strategy=next_strategy,
                language=lang,
                repair_hints=repair_hints,
            )

            if attempt == max_attempts:
                failure_cats = PatternExtractor.extract_categories(test_errors)
                # Add security categories
                for f in artifact.security_findings:
                    if f.severity in (SecurityLevel.CRITICAL, SecurityLevel.HIGH):
                        failure_cats.append(f.category)
                failure_cats = list(set(failure_cats))

                self.loop.record_outcome(False, attempt, quality.overall, failure_cats)
                self.governance.log_audit("pipeline_failed", "orchestrator", {
                    "error": "LOOP_EXHAUSTED",
                    "attempts": attempt,
                    "final_score": quality.overall,
                    "failure_categories": failure_cats,
                    "loop_metrics": self.loop.get_metrics(),
                    "memory_stats": self.portable_memory.stats(),
                })
                raise RuntimeError(
                    f"LOOP_EXHAUSTED after {attempt} attempts "
                    f"(score={quality.overall:.2f}, failures={failure_cats})"
                )

        assert artifact is not None

        # 6. Human Approval
        if not self.governance.require_human_approval(artifact):
            self.governance.log_audit(
                "pipeline_rejected", "orchestrator",
                error="Human approval rejected",
            )
            artifact.status = ApprovalStatus.REJECTED
            return artifact

        # 7. Deployment Stage (CONSTITUTION.md section 2)
        deployment_records = []
        for file_rel_path in artifact.generated_files:
            source_path = os.path.join(requirement.target_folder, file_rel_path)
            target_path = source_path
            deploy_record = self.deployer.deploy(
                artifact_path=source_path,
                target_path=target_path,
                language=requirement.language.value,
            )
            deployment_records.append(deploy_record)
            if deploy_record.status not in (ApprovalStatus.DEPLOYED,):
                artifact.status = deploy_record.status
                self.governance.log_audit(
                    "deployment_failed", "orchestrator",
                    {
                        "deployment_id": deploy_record.deployment_id,
                        "status": deploy_record.status.value,
                        "target_path": deploy_record.target_path,
                        "reason": deploy_record.rollback_reason,
                    },
                )
                return artifact

        artifact.status = ApprovalStatus.DEPLOYED
        self.governance.log_audit("deployment_complete", "orchestrator", {
            "deployment_count": len(deployment_records),
            "deployment_ids": [r.deployment_id for r in deployment_records],
            "status": artifact.status.value,
        })
        self.governance.log_audit("pipeline_success", "orchestrator", {
            "status": artifact.status.value,
            "generated_files": artifact.generated_files,
            "deployment_count": len(deployment_records),
        })
        return artifact

    def run_pipeline_for_user(
        self,
        user: "UserIdentity",
        requirement: Requirement,
        architecture: str,
        modules: list[str],
    ) -> Artifact:
        """Execute pipeline with access control enforcement.

        This is the ONLY entry point that external users may call.
        It validates tier capabilities BEFORE any code generation begins.
        The internal run_pipeline() remains for operator use only.

        Users never touch files, contracts, or source code directly.
        They submit requirements and receive artifacts. Nothing else.
        """
        from .access_control import AccessGate

        gate = AccessGate()
        language = requirement.language.value if hasattr(requirement.language, 'value') else str(requirement.language)
        target = str(requirement.target_folder) if requirement.target_folder else "/tmp/atlas-output"

        decision = gate.validate_requirement(
            user=user,
            description=requirement.description,
            language=language,
            modules=modules,
            target_folder=target,
        )

        if not decision.allowed:
            self.governance.log_audit(
                "access_denied", "orchestrator",
                {
                    "user_id": user.user_id,
                    "tier": user.tier.value,
                    "action": decision.requested_action,
                    "reason": decision.reason,
                },
            )
            raise PermissionError(decision.reason)

        # Access granted - delegate to internal pipeline
        logger.info(
            "User %s (tier=%s) authorized for pipeline execution",
            user.user_id, user.tier.value,
        )
        return self.run_pipeline(
            requirement=requirement,
            architecture=architecture,
            modules=modules,
        )
