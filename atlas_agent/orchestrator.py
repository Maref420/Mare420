"""
Orchestrator for ATLAS AI Agent
Coordinates the workflow between Governance, Generator, and Validator
"""
from typing import Dict, Any, List
from .models import Requirement, Specification, Artifact, ApprovalStatus
from .governance import GovernanceEngine
from .generator import GeneratorEngine
from .validator import ValidatorEngine
from .config import settings
import os

class Orchestrator:
    """
    Main orchestrator for the code generation pipeline.
    """

    def __init__(self):
        self.governance = GovernanceEngine()
        self.generator = GeneratorEngine()
        self.validator = ValidatorEngine()

    def run_pipeline(self, requirement: Requirement, architecture: str, modules: List[str]) -> Artifact:
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

        # 3. Generate Code
        generated_files = self.generator.generate_project(spec, requirement.target_folder)
        
        # 4. Create Artifact
        artifact = Artifact(
            requirement=requirement,
            specification=spec,
            generated_files=generated_files
        )

        # 5. Validate Generated Code
        for file_path in generated_files:
            syntax_result = self.validator.check_syntax(file_path, requirement.language.value)
            artifact.test_results.append(syntax_result)
            
            security_findings = self.validator.run_security_scan(file_path)
            artifact.security_findings.extend(security_findings)

        # 6. Governance Validation
        if not self.governance.validate_artifact(artifact):
            self.governance.log_audit("pipeline_failed", "orchestrator", error="Governance validation failed")
            raise ValueError("Governance validation failed")

        # 7. Human Approval
        if not self.governance.require_human_approval(artifact):
            self.governance.log_audit("pipeline_rejected", "orchestrator", error="Human approval rejected")
            artifact.status = ApprovalStatus.REJECTED
            return artifact

        artifact.status = ApprovalStatus.APPROVED
        self.governance.log_audit("pipeline_success", "orchestrator", {"artifact": artifact.model_dump_json()})
        
        return artifact
