"""
Validator Engine for ATLAS AI Agent
Validates generated code for syntax, security, and policy compliance
"""
import ast
import os
import subprocess

from .models import SecurityFinding, SecurityLevel, TestResult


class ValidatorEngine:
    """
    Validates generated code artifacts.
    """

    def check_syntax(self, file_path: str, language: str) -> TestResult:
        """
        Check syntax of generated code.
        """
        try:
            if language == "python":
                with open(file_path, 'r') as f:
                    source = f.read()
                ast.parse(source)
                return TestResult(test_name="syntax_check", passed=True, duration_ms=0.1)
            elif language == "rust":
                result = subprocess.run(
                    ["rustc", "--emit=metadata", file_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )
                return TestResult(
                    test_name="syntax_check",
                    passed=result.returncode == 0,
                    duration_ms=0.1,
                    output=result.stdout,
                    errors=result.stderr.splitlines() if result.stderr else []
                )
            elif language == "go":
                project_dir = os.path.abspath(file_path)

                format_result = subprocess.run(
                    ["gofmt", "-l", "."],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )

                if format_result.returncode != 0:
                    return TestResult(
                        test_name="syntax_check",
                        passed=False,
                        duration_ms=0.1,
                        output=format_result.stdout,
                        errors=format_result.stderr.splitlines()
                        if format_result.stderr else []
                    )

                if format_result.stdout.strip():
                    return TestResult(
                        test_name="syntax_check",
                        passed=False,
                        duration_ms=0.1,
                        output=format_result.stdout,
                        errors=["Go source is not gofmt-formatted"]
                    )

                vet_result = subprocess.run(
                    ["go", "vet", "./..."],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )

                if vet_result.returncode != 0:
                    return TestResult(
                        test_name="syntax_check",
                        passed=False,
                        duration_ms=0.1,
                        output=vet_result.stdout,
                        errors=vet_result.stderr.splitlines()
                        if vet_result.stderr else []
                    )

                test_result = subprocess.run(
                    ["go", "test", "./..."],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )

                if test_result.returncode != 0:
                    return TestResult(
                        test_name="syntax_check",
                        passed=False,
                        duration_ms=0.1,
                        output=test_result.stdout,
                        errors=test_result.stderr.splitlines()
                        if test_result.stderr else []
                    )

                race_result = subprocess.run(
                    ["go", "test", "-race", "./..."],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )

                if race_result.returncode != 0:
                    return TestResult(
                        test_name="syntax_check",
                        passed=False,
                        duration_ms=0.1,
                        output=race_result.stdout,
                        errors=race_result.stderr.splitlines()
                        if race_result.stderr else []
                    )

                build_result = subprocess.run(
                    ["go", "build", "./..."],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )

                return TestResult(
                    test_name="syntax_check",
                    passed=build_result.returncode == 0,
                    duration_ms=0.1,
                    output=build_result.stdout,
                    errors=build_result.stderr.splitlines()
                    if build_result.stderr else []
                )
        except SyntaxError as e:
            return TestResult(test_name="syntax_check", passed=False, duration_ms=0.1, errors=[str(e)])
        except Exception as e:  # noqa: BLE001
            return TestResult(test_name="syntax_check", passed=False, duration_ms=0.1, errors=[str(e)])
        
        return TestResult(test_name="syntax_check", passed=False, duration_ms=0.1, errors=["Unsupported language"])

    def run_security_scan(self, file_path: str, language: str) -> list[SecurityFinding]:
        """
        Run the language-appropriate security validation.

        External scanners are not silently ignored when unavailable.
        The caller supplies the target language explicitly.

        Args:
            file_path: File or project directory to scan.
            language: Target programming language.

        Returns:
            Security findings produced by the configured validator.

        Raises:
            RuntimeError: If a required security scanner is unavailable.

        """
        findings = []
        try:
            if language == "python":
                result = subprocess.run(
                    ["bandit", "-r", file_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if result.returncode != 0:
                    findings.append(SecurityFinding(
                        severity=SecurityLevel.MEDIUM,
                        category="security_scan",
                        message="Bandit scan found issues",
                        file_path=file_path,
                        suggestion=result.stderr.strip() or "Review Bandit output",
                    ))
                return findings

            if language == "go":
                result = subprocess.run(
                    ["go", "vet", "./..."],
                    cwd=os.path.abspath(file_path),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if result.returncode != 0:
                    findings.append(SecurityFinding(
                        severity=SecurityLevel.HIGH,
                        category="go_security_validation",
                        message="Go vet reported issues",
                        file_path=file_path,
                        suggestion=result.stderr.strip() or "Review go vet output",
                    ))
                return findings

            raise ValueError(f"Unsupported security scan language: {language}")
        except FileNotFoundError as e:
            raise RuntimeError(
                f"Required security scanner is unavailable for {language}: {e.filename}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"Security scan timed out for {language}: {file_path}"
            ) from e


    def run_tests(self, target_dir: str, language: str) -> list[TestResult]:
        """
        Run tests in the target directory.
        """
        results = []
        try:
            if language == "python":
                result = subprocess.run(
                    ["python3", "-m", "pytest", target_dir],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False
                )
                results.append(TestResult(
                    test_name="unit_tests",
                    passed=result.returncode == 0,
                    duration_ms=1000,
                    output=result.stdout,
                    errors=result.stderr.split('\n') if result.stderr else []
                ))
        except FileNotFoundError:
            results.append(TestResult(test_name="unit_tests", passed=False, duration_ms=0, errors=["pytest not found"]))
        except subprocess.TimeoutExpired:
            results.append(TestResult(test_name="unit_tests", passed=False, duration_ms=60000, errors=["Test timeout"]))
            
        return results
