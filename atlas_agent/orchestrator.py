import os
import time
import logging

logger = logging.getLogger(__name__)
"""
Orchestrator for ATLAS AI Agent
Coordinates the workflow between Governance, Generator, and Validator
"""

__all__ = ['Orchestrator']

from .generator import GeneratorEngine
from .governance import GovernanceEngine
from .models import ApprovalStatus, Artifact, Requirement, SecurityLevel, Specification
from .validator import ValidatorEngine
from .deployment import DeploymentEngine
from .self_correcting_loop import SelfCorrectingLoop, QualityScore
from .memory import LearningMemory


class Orchestrator:
    """
    Main orchestrator for the code generation pipeline.
    """

    def __init__(self) -> None:
        self.governance = GovernanceEngine()
        self.deployer = DeploymentEngine(governance_engine=self.governance)
        self.generator = GeneratorEngine()
        self.validator = ValidatorEngine()
        self.memory = LearningMemory()
        self.loop = SelfCorrectingLoop()

    def run_pipeline(self, requirement: Requirement, architecture: str, modules: list[str]) -> Artifact:
        """
        Execute the full code generation pipeline.
        """
        self.governance.log_audit("pipeline_start", "orchestrator", {"requirement": requirement.model_dump_json()})

        # 1. Create Specification
        spec = Specification(
            requirement=requirement,
            architecture=architecture,
            modules=[{"name": m} for m in modules],
            dependencies=[]
        )

        # 2. Validate Specification
        if not self.governance.validate_specification(spec):
            self.governance.log_audit("pipeline_failed", "orchestrator", error="Specification validation failed")
            raise ValueError("Specification validation failed")

# 3. Generate, validate, and repair code (Self-Correcting Loop v2)
        max_attempts = self.loop.MAX_ATTEMPTS
        repair_context = None
        artifact = None
        previous_code = ""
        attempt_history = []
        lang = requirement.language.value
        quality = QualityScore()

        for attempt in range(1, max_attempts + 1):
            # Determine repair strategy based on attempt number
            strategy = self.loop.determine_strategy(attempt, [])

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

            # Compute multi-dimensional quality score
            quality = self.loop.compute_quality_score(
                syntax_passed=all_syntax_passed,
                security_findings=artifact.security_findings,
                generated_files=generated_files,
                language=lang,
            )

            # Collect errors for attempt record
            failed_results = [r for r in artifact.test_results if not r.passed]
            test_errors = [e for r in failed_results for e in r.errors]
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
                    code_len += len(open(fp).read())

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
                "Attempt %d/%d: score=%.2f strategy=%s errors=%d security=%d latency=%.1fs",
                attempt, max_attempts, quality.overall, strategy.value,
                len(test_errors), len(security_errors), latency,
            )

            # 5. Check if passed (quality threshold + governance)
            if quality.passed and self.governance.validate_artifact(artifact):
                self.loop.record_outcome(True, attempt, quality.overall, [])
                self.governance.log_audit("pipeline_success", "orchestrator", {
                    "attempts": attempt,
                    "score": quality.overall,
                    "strategy": strategy.value,
                    "loop_metrics": self.loop.get_metrics(),
                })
                break


            # Build structured repair context for next attempt (full regen fallback)
            anti_patterns = list(self.memory.get_anti_patterns())

            # Read previous code for PATCH strategy
            if source_files:
                first_file = os.path.join(requirement.target_folder, source_files[0])
                if os.path.exists(first_file):
                    with open(first_file) as f:
                        previous_code = f.read()

            next_strategy = self.loop.determine_strategy(attempt + 1, test_errors)
            repair_context = self.loop.build_structured_repair_context(
                previous_code=previous_code,
                errors=test_errors,
                security_findings=security_errors,
                anti_patterns=anti_patterns,
                attempt_history=attempt_history,
                strategy=next_strategy,
            )

            if attempt == max_attempts:
                failure_cats = list(set(
                    [e.split(":")[0].strip() for e in test_errors[:3]] +
                    [f.category for f in artifact.security_findings
                     if f.severity in (SecurityLevel.CRITICAL, SecurityLevel.HIGH)]
                ))
                self.loop.record_outcome(False, attempt, quality.overall, failure_cats)
                self.governance.log_audit("pipeline_failed", "orchestrator", {
                    "error": "LOOP_EXHAUSTED",
                    "attempts": attempt,
                    "final_score": quality.overall,
                    "failure_categories": failure_cats,
                    "loop_metrics": self.loop.get_metrics(),
                })
                raise RuntimeError(
                    f"LOOP_EXHAUSTED after {attempt} attempts "
                    f"(score={quality.overall:.2f}, failures={failure_cats})"
                )

        assert artifact is not None


        # 6. Human Approval
        if not self.governance.require_human_approval(artifact):
            self.governance.log_audit(
                "pipeline_rejected",
                "orchestrator",
                error="Human approval rejected",
            )
            artifact.status = ApprovalStatus.REJECTED
            return artifact

        # CONSTITUTION.md §2: Deployment Stage
        # Deploy all generated files recorded in artifact.generated_files.
        deployment_records = []
        for file_rel_path in artifact.generated_files:
            source_path = os.path.join(
                requirement.target_folder,
                file_rel_path,
            )
            target_path = source_path

            deploy_record = self.deployer.deploy(
                artifact_path=source_path,
                target_path=target_path,
                language=requirement.language.value,
            )
            deployment_records.append(deploy_record)

            if deploy_record.status not in (
                ApprovalStatus.DEPLOYED,
            ):
                artifact.status = deploy_record.status
                self.governance.log_audit(
                    "deployment_failed",
                    "orchestrator",
                    {
                        "deployment_id": deploy_record.deployment_id,
                        "status": deploy_record.status.value,
                        "target_path": deploy_record.target_path,
                        "reason": deploy_record.rollback_reason,
                    },
                )
                return artifact

        artifact.status = ApprovalStatus.DEPLOYED
        self.governance.log_audit(
            "deployment_complete",
            "orchestrator",
            {
                "deployment_count": len(deployment_records),
                "deployment_ids": [r.deployment_id for r in deployment_records],
                "status": artifact.status.value,
            },
        )

        # CONSTITUTION.md §2: Deployment Stage
        target_file = os.path.join(
            requirement.target_folder,
            artifact.file_path,
        )
        deploy_record = self.deployer.deploy(
            artifact_path=target_file,
            target_path=target_file,
            language=requirement.language.value,
        )
        artifact.status = deploy_record.status
        self.governance.log_audit(
            "deployment_complete",
            "orchestrator",
            {
                "deployment_id": deploy_record.deployment_id,
                "status": deploy_record.status.value,
                "target_path": deploy_record.target_path,
            },
        )

        artifact.status = ApprovalStatus.APPROVED
        self.governance.log_audit(
            "pipeline_success",
            "orchestrator",
            {"artifact": artifact.model_dump_json()},
        )

        return artifact