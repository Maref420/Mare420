"""
Orchestrator for ATLAS AI Agent
Coordinates the workflow between Governance, Generator, and Validator
"""
from .generator import GeneratorEngine
from .governance import GovernanceEngine
from .models import ApprovalStatus, Artifact, Requirement, SecurityLevel, Specification
from .validator import ValidatorEngine


class Orchestrator:
    """
    Main orchestrator for the code generation pipeline.
    """

    def __init__(self) -> None:
        self.governance = GovernanceEngine()
        self.generator = GeneratorEngine()
        self.validator = ValidatorEngine()

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

        # 3. Generate, validate, and repair code
        max_attempts = 5
        repair_context = None
        artifact = None

        for attempt in range(1, max_attempts + 1):
            generated_files = self.generator.generate_project(
                spec,
                requirement.target_folder,
                repair_context=repair_context,
            )

            artifact = Artifact(
                requirement=requirement,
                specification=spec,
                generated_files=generated_files,
            )

            # 4. Validate Generated Code
            if requirement.language.value == "go":
                syntax_result = self.validator.check_syntax(
                    requirement.target_folder,
                    requirement.language.value,
                )
                artifact.test_results.append(syntax_result)

                for file_path in generated_files:
                    security_findings = self.validator.run_security_scan(
                        file_path,
                        requirement.language.value,
                    )
                    artifact.security_findings.extend(security_findings)
            else:
                for file_path in generated_files:
                    syntax_result = self.validator.check_syntax(
                        file_path,
                        requirement.language.value,
                    )
                    artifact.test_results.append(syntax_result)

                    security_findings = self.validator.run_security_scan(
                        file_path,
                        requirement.language.value,
                    )
                    artifact.security_findings.extend(security_findings)

            # 5. Governance Validation
            if self.governance.validate_artifact(artifact):
                break

            # Collect ALL validation failures for repair context
            failed_results = [
                result
                for result in artifact.test_results
                if not result.passed
            ]
            test_errors = [
                error
                for result in failed_results
                for error in result.errors
            ]

            # CRITICAL: Include security findings in repair feedback
            security_errors = [
                f"[{f.severity.value.upper()}] {f.category}: {f.message} -> {f.suggestion}"
                for f in artifact.security_findings
                if f.severity in (SecurityLevel.CRITICAL, SecurityLevel.HIGH)
            ]

            repair_parts = test_errors + security_errors
            repair_context = "\n".join(repair_parts) if repair_parts else None


            if attempt == max_attempts:
                self.governance.log_audit(
                    "pipeline_failed",
                    "orchestrator",
                    error="LOOP_EXHAUSTED",
                )
                raise RuntimeError("LOOP_EXHAUSTED")

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

        artifact.status = ApprovalStatus.APPROVED
        self.governance.log_audit(
            "pipeline_success",
            "orchestrator",
            {"artifact": artifact.model_dump_json()},
        )

        return artifact
