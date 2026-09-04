from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atlas_agent.models import (
    ApprovalStatus,
    Language,
    Requirement,
)


def make_requirement(tmp_path: Path) -> Requirement:
    return Requirement(
        description="Generate a valid Python program",
        language=Language.PYTHON,
        project_name="loop-test",
        target_folder=str(tmp_path),
    )


def make_generator(responses):
    generator = MagicMock()
    generator.generate_project.side_effect = responses
    return generator


def make_validator(results):
    validator = MagicMock()
    validator.check_syntax.side_effect = results
    validator.run_security_scan.return_value = []
    return validator


def test_first_attempt_succeeds(tmp_path):
    from atlas_agent.models import TestResult
    from atlas_agent.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    orchestrator.generator = make_generator([["main.py"]])
    orchestrator.validator = make_validator([
        TestResult(test_name="syntax_check", passed=True, duration_ms=1.0)
    ])
    orchestrator.governance.require_human_approval = MagicMock(return_value=False)

    artifact = orchestrator.run_pipeline(
        make_requirement(tmp_path),
        "simple architecture",
        ["main"],
    )

    assert artifact.status == ApprovalStatus.REJECTED
    assert orchestrator.generator.generate_project.call_count == 1


def test_first_attempt_fails_second_succeeds(tmp_path):
    from atlas_agent.models import TestResult
    from atlas_agent.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    orchestrator.generator = make_generator([
        ["main.py"],
        ["main.py"],
    ])
    orchestrator.validator = make_validator([
        TestResult(
            test_name="syntax_check",
            passed=False,
            duration_ms=1.0,
            errors=["SyntaxError: invalid syntax"],
        ),
        TestResult(test_name="syntax_check", passed=True, duration_ms=1.0),
    ])
    orchestrator.governance.require_human_approval = MagicMock(return_value=False)

    artifact = orchestrator.run_pipeline(
        make_requirement(tmp_path),
        "simple architecture",
        ["main"],
    )

    assert artifact.status == ApprovalStatus.REJECTED
    assert orchestrator.generator.generate_project.call_count == 2


def test_multiple_failures_then_success(tmp_path):
    from atlas_agent.models import TestResult
    from atlas_agent.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    orchestrator.generator = make_generator([
        ["main.py"],
        ["main.py"],
        ["main.py"],
        ["main.py"],
    ])
    orchestrator.validator = make_validator([
        TestResult(test_name="syntax_check", passed=False, duration_ms=1.0,
                   errors=["error-1"]),
        TestResult(test_name="syntax_check", passed=False, duration_ms=1.0,
                   errors=["error-2"]),
        TestResult(test_name="syntax_check", passed=False, duration_ms=1.0,
                   errors=["error-3"]),
        TestResult(test_name="syntax_check", passed=True, duration_ms=1.0),
    ])
    orchestrator.governance.require_human_approval = MagicMock(return_value=False)

    artifact = orchestrator.run_pipeline(
        make_requirement(tmp_path),
        "simple architecture",
        ["main"],
    )

    assert artifact.status == ApprovalStatus.REJECTED
    assert orchestrator.generator.generate_project.call_count == 4


def test_five_failures_exhaust_loop(tmp_path):
    from atlas_agent.models import TestResult
    from atlas_agent.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    orchestrator.generator = make_generator([["main.py"]] * 5)
    orchestrator.validator = make_validator([
        TestResult(
            test_name="syntax_check",
            passed=False,
            duration_ms=1.0,
            errors=[f"error-{i}"],
        )
        for i in range(1, 6)
    ])
    orchestrator.governance.require_human_approval = MagicMock(return_value=True)

    with pytest.raises(RuntimeError, match="LOOP_EXHAUSTED"):
        orchestrator.run_pipeline(
            make_requirement(tmp_path),
            "simple architecture",
            ["main"],
        )

    assert orchestrator.generator.generate_project.call_count == 5
    orchestrator.governance.require_human_approval.assert_not_called()


def test_validation_failure_is_included_in_repair_prompt(tmp_path):
    from atlas_agent.models import TestResult
    from atlas_agent.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    orchestrator.generator = make_generator([
        ["main.py"],
        ["main.py"],
    ])
    orchestrator.validator = make_validator([
        TestResult(
            test_name="syntax_check",
            passed=False,
            duration_ms=1.0,
            errors=["SyntaxError: invalid syntax at line 4"],
        ),
        TestResult(test_name="syntax_check", passed=True, duration_ms=1.0),
    ])
    orchestrator.governance.require_human_approval = MagicMock(return_value=False)

    orchestrator.run_pipeline(
        make_requirement(tmp_path),
        "simple architecture",
        ["main"],
    )

    second_call = orchestrator.generator.generate_project.call_args_list[1]
    repair_context = second_call.kwargs.get("repair_context")

    assert repair_context is not None
    assert "SyntaxError: invalid syntax at line 4" in repair_context


def test_successful_validation_preserves_governance_and_approval(tmp_path):
    from atlas_agent.models import TestResult
    from atlas_agent.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    orchestrator.generator = make_generator([["main.py"]])
    orchestrator.validator = make_validator([
        TestResult(test_name="syntax_check", passed=True, duration_ms=1.0)
    ])

    approval = MagicMock(return_value=True)
    orchestrator.governance.require_human_approval = approval

    # Mock deployer — unit test should not depend on filesystem
    from atlas_agent.models import DeploymentRecord
    mock_deploy_record = DeploymentRecord(
        deployment_id="test-deploy-001",
        artifact_path="main.py",
        target_path=str(tmp_path / "main.py"),
        status=ApprovalStatus.DEPLOYED,
        timestamp=0.0,
        audit_event_id="test-audit-001",
    )
    orchestrator.deployer = MagicMock()
    orchestrator.deployer.deploy.return_value = mock_deploy_record

    artifact = orchestrator.run_pipeline(
        make_requirement(tmp_path),
        "simple architecture",
        ["main"],
    )

    assert artifact.status == ApprovalStatus.DEPLOYED
    approval.assert_called_once_with(artifact)
    orchestrator.deployer.deploy.assert_called_once()
