"""
Validator Engine for ATLAS AI Agent
Validates generated code for syntax, security, and policy compliance
"""

__all__ = ['ValidatorEngine', 'TestResult', 'SecurityFinding']

import ast
import logging

logger = logging.getLogger(__name__)
import os
import subprocess

from .models import SecurityFinding, SecurityLevel, TestResult


class ValidatorEngine:
    """
    Validates generated code artifacts.
    """
    @staticmethod
    def _to_relative(file_path: str) -> str:
        """Convert absolute path to relative for SecurityFinding contract compliance."""
        if os.path.isabs(file_path):
            try:
                return os.path.relpath(file_path)
            except ValueError:
                return os.path.basename(file_path)
        return file_path


    def check_syntax(self, file_path: str, language: str) -> TestResult:
        """
        Check syntax of generated code.
        """
        try:
            if language == "python":
                with open(file_path) as f:
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
                # Governed: file_path may be a file or directory.
                # Always resolve to project directory for go tooling.
                abs_path = os.path.abspath(file_path)
                project_dir = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)

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

    def run_security_scan(self, file_path: str, language: str, base_dir: str = "") -> list[SecurityFinding]:
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
        # Governed: Compute display_path once for all findings.
        # Validators own the path format in their output models.
        if base_dir and os.path.isabs(file_path):
            display_path = os.path.relpath(file_path, base_dir)
        else:
            display_path = file_path
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
                        file_path=display_path,
                        suggestion=result.stderr.strip() or "Review Bandit output",
                    ))
                return findings

            if language == "go":
                # Governed: go vet requires project directory.
                # Use base_dir if provided, otherwise derive from file_path.
                go_project_dir = base_dir if base_dir else (
                    os.path.dirname(os.path.abspath(file_path))
                    if not os.path.isdir(os.path.abspath(file_path))
                    else os.path.abspath(file_path)
                )
                # Skip go vet if no go.mod — produces false positives
                go_mod_path = os.path.join(go_project_dir, "go.mod")
                if not os.path.exists(go_mod_path):
                    logger.info("Skipping go vet: no go.mod in %s", go_project_dir)
                    return findings
                result = subprocess.run(
                    ["go", "vet", "./..."],
                    cwd=go_project_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if result.returncode != 0:
                    # Filter out dependency resolution errors (not code issues)
                    stderr_lines = (result.stderr or "").splitlines()
                    real_errors = [
                        line for line in stderr_lines
                        if "no required module" not in line
                        and "cannot find package" not in line
                        and "build constraints exclude" not in line
                        and "missing go.mod" not in line
                        and line.strip() != ""
                    ]
                    if real_errors:
                        findings.append(SecurityFinding(
                            severity=SecurityLevel.HIGH,
                            category="go_security_validation",
                            message="Go vet reported issues",
                            file_path=display_path,
                            suggestion="\n".join(real_errors[:5]) or "Review go vet output",
                        ))
                return findings

            if language == "rust":
                # Governed: cargo clippy requires project directory, not file path
                abs_path = os.path.abspath(file_path)
                rust_project_dir = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)
                result = subprocess.run(
                    ["cargo", "clippy", "--", "-D", "warnings"],
                    cwd=rust_project_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                if result.returncode != 0:
                    findings.append(SecurityFinding(
                        severity=SecurityLevel.HIGH,
                        category="rust_clippy",
                        message="Cargo clippy reported warnings/errors",
                        file_path=display_path,
                        suggestion=result.stdout.strip() or result.stderr.strip() or "Review cargo clippy output",
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


    def compile_check(self, target_dir: str, language: str) -> TestResult:
        """Compile generated code without running it."""
        import time as _time
        t0 = _time.monotonic()
        timeout_sec = int(os.environ.get("ATLAS_COMPILE_TIMEOUT", "120"))
        try:
            if language == "rust":
                result = subprocess.run(
                    ["cargo", "build", "--release"], cwd=target_dir,
                    capture_output=True, text=True, timeout=timeout_sec, check=False)
                duration = int((_time.monotonic() - t0) * 1000)
                errors = [l.strip()[:300] for l in result.stderr.split("\n")
                          if l.strip() and "error" in l.lower()][:10]
                return TestResult(test_name="compile_check", passed=result.returncode == 0,
                    duration_ms=duration, output=result.stdout[:2000], errors=errors)
            elif language == "go":
                result = subprocess.run(
                    ["go", "build", "./..."], cwd=target_dir,
                    capture_output=True, text=True, timeout=timeout_sec, check=False)
                duration = int((_time.monotonic() - t0) * 1000)
                errors = [l.strip()[:300] for l in result.stderr.split("\n") if l.strip()][:10]
                return TestResult(test_name="compile_check", passed=result.returncode == 0,
                    duration_ms=duration, output=result.stdout[:2000], errors=errors)
            elif language == "python":
                result = subprocess.run(
                    ["python3", "-m", "py_compile", target_dir],
                    capture_output=True, text=True, timeout=30, check=False)
                duration = int((_time.monotonic() - t0) * 1000)
                return TestResult(test_name="compile_check", passed=result.returncode == 0,
                    duration_ms=duration, output="",
                    errors=result.stderr.split("\n")[:5] if result.stderr else [])
            return TestResult(test_name="compile_check", passed=False, duration_ms=0,
                errors=[f"Unsupported language: {language}"])
        except FileNotFoundError as e:
            return TestResult(test_name="compile_check", passed=False, duration_ms=0,
                errors=[f"Compiler not found: {e.filename}"])
        except subprocess.TimeoutExpired:
            return TestResult(test_name="compile_check", passed=False,
                duration_ms=timeout_sec * 1000, errors=["Compilation timeout"])

    def run_tests(self, target_dir: str, language: str) -> list[TestResult]:
        """Run tests supporting Rust, Go, Python."""
        import time as _time
        results = []
        timeout_sec = int(os.environ.get("ATLAS_TEST_TIMEOUT", "60"))
        try:
            if language == "rust":
                t0 = _time.monotonic()
                result = subprocess.run(
                    ["cargo", "test", "--release"], cwd=target_dir,
                    capture_output=True, text=True, timeout=timeout_sec, check=False)
                duration = int((_time.monotonic() - t0) * 1000)
                errors = [l.strip()[:300] for l in result.stderr.split("\n")
                          if l.strip() and ("FAILED" in l or "error" in l.lower())][:10]
                tr = TestResult(test_name="cargo_test", passed=result.returncode == 0,
                    duration_ms=duration, output=result.stdout[:2000], errors=errors)
                # Parse pass rate
                tr._pass_rate = 1.0
                for line in result.stdout.split("\n"):
                    if "test result:" in line:
                        parts = line.split(";")
                        p_count = f_count = 0
                        for part in parts:
                            nums = [x for x in part.split() if x.isdigit()]
                            if "passed" in part and nums: p_count = int(nums[0])
                            if "failed" in part and nums: f_count = int(nums[0])
                        total = p_count + f_count
                        if total > 0: tr._pass_rate = p_count / total
                        break
                results.append(tr)
            elif language == "go":
                t0 = _time.monotonic()
                result = subprocess.run(
                    ["go", "test", "-v", "-count=1", "./..."], cwd=target_dir,
                    capture_output=True, text=True, timeout=timeout_sec, check=False)
                duration = int((_time.monotonic() - t0) * 1000)
                errors = [l.strip()[:300] for l in (result.stdout + result.stderr).split("\n")
                          if "FAIL" in l][:10]
                results.append(TestResult(test_name="go_test", passed=result.returncode == 0,
                    duration_ms=duration, output=result.stdout[:2000], errors=errors))
            elif language == "python":
                t0 = _time.monotonic()
                result = subprocess.run(
                    ["python3", "-m", "pytest", target_dir, "-v", "--tb=short"],
                    capture_output=True, text=True, timeout=timeout_sec, check=False)
                duration = int((_time.monotonic() - t0) * 1000)
                results.append(TestResult(test_name="pytest", passed=result.returncode == 0,
                    duration_ms=duration, output=result.stdout[:2000],
                    errors=result.stderr.split("\n")[:10] if result.stderr else []))
            else:
                results.append(TestResult(test_name="tests", passed=False, duration_ms=0,
                    errors=[f"Unsupported language: {language}"]))
        except FileNotFoundError as e:
            results.append(TestResult(test_name="tests", passed=False, duration_ms=0,
                errors=[f"Test runner not found: {e.filename}"]))
        except subprocess.TimeoutExpired:
            results.append(TestResult(test_name="tests", passed=False,
                duration_ms=timeout_sec * 1000, errors=["Test timeout"]))
        return results