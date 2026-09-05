"""Code Generator Engine — Contract-Based LLM Invocation.

Governed by: contracts/schemas/ai/llm-invocation-v1.json
Pipeline: Privacy Guard → §17 Check → Memory Context → LLM Call → Clean Output

This module does NOT send raw prompts to LLM. Every invocation passes through:
1. Privacy sanitization (strip sensitive data)
2. §17 restriction enforcement (reject prohibited categories)
3. Learning memory context (approved/rejected examples + anti-patterns)
4. Contract-validated LLM call (with fallback)
"""

__all__ = ['GeneratorEngine']


import hashlib
import logging
import os
import re
from typing import Any, Optional

from .llm_client import LLMClient
from .memory import LearningMemory, Decision
from .memory.experience import Source, Method, Artifact as MemArtifact

logger = logging.getLogger(__name__)

# CONSTITUTION.md §17 — Hardcoded for defense-in-depth
# §17 restriction check delegated to LLMClient → RestrictionGuard
# Rules: contracts/schemas/ai/restriction-rules-v1.json

# Privacy patterns — data that must NEVER leave VPS
SENSITIVE_PATTERNS = [
    r'(?i)api[_-]?key\s*[=:]\s*\S+',
    r'(?i)password\s*[=:]\s*\S+',
    r'(?i)secret\s*[=:]\s*\S+',
    r'(?i)token\s*[=:]\s*\S+',
    r'(?i)gsk_[a-zA-Z0-9]+',
    r'(?i)sk-[a-zA-Z0-9]+',
    r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',  # IP addresses
]


class GenerationRejectedError(Exception):
    """Raised when generation is rejected by governance or §17."""
    pass


class GeneratorEngine:
    """Contract-based code generator with learning memory."""

    def __init__(self) -> None:
        self.llm = LLMClient()
        self.memory = LearningMemory()

    def _sanitize(self, text: str) -> str:
        """Strip sensitive data before sending to external LLM."""
        sanitized = text
        for pattern in SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, "[REDACTED]", sanitized)
        return sanitized

    # §17 check handled by LLMClient → RestrictionGuard

    def _build_context(self, language: str, module: str, requirement: str) -> str:
        """Build intelligent context from learning memory."""
        positives = self.memory.get_positive(language, module, limit=2)
        negatives = self.memory.get_negative(language, limit=2)
        anti_patterns = self.memory.get_anti_patterns()

        parts = []

        if positives:
            parts.append("APPROVED PATTERNS (follow these):")
            for exp in positives:
                parts.append(
                    f"  - [{exp.artifact.module}] score={exp.outcome.quality_score:.2f} "
                    f"reason='{exp.outcome.reason}'"
                )

        if negatives:
            parts.append("REJECTED PATTERNS (DO NOT repeat):")
            for exp in negatives:
                parts.append(
                    f"  - reason='{exp.outcome.reason}' "
                    f"anti_patterns={exp.anti_patterns}"
                )

        if anti_patterns:
            parts.append(f"ANTI-PATTERNS TO AVOID: {', '.join(sorted(anti_patterns))}")

        return "\n".join(parts) if parts else ""

    # Python stdlib module names that must NOT be used as file names
    PYTHON_STDLIB_CONFLICTS = {
        "math", "os", "sys", "json", "time", "re", "io", "abc",
        "ast", "csv", "ssl", "subprocess", "collections", "typing",
        "logging", "unittest", "random", "hashlib", "datetime",
        "pathlib", "functools", "itertools", "copy", "socket",
        "threading", "multiprocessing", "email", "html", "http",
        "urllib", "sqlite3", "pickle", "shelve", "struct", "codecs",
        "decimal", "fractions", "statistics", "secrets", "uuid",
    }

    def _safe_module_name(self, name: str, lang: str) -> str:
        """Ensure module name doesn't conflict with stdlib."""
        if lang == "python" and name.lower() in self.PYTHON_STDLIB_CONFLICTS:
            safe = f"{name}_module"
            logger.warning("Module name '%s' conflicts with stdlib, renamed to '%s'", name, safe)
            return safe
        return name

    def _clean_code(self, code: str) -> str:
        """Remove markdown fences and extra whitespace."""
        code = re.sub(r'^```\w*\s*', '', code, flags=re.MULTILINE)
        code = re.sub(r'^```\s*$', '', code, flags=re.MULTILINE)
        return code.strip()

    def _get_extension(self, lang: str) -> str:
        extensions = {"python": "py", "rust": "rs", "go": "go"}
        return extensions.get(lang, "txt")

    def generate_project(
        self,
        spec: Any,
        target_dir: str,
        repair_context: Optional[str] = None,
    ) -> list[str]:
        """Generate project files per governed pipeline.

        Pipeline per module:
        1. Privacy sanitize requirement
        2. §17 restriction check
        3. Build memory context
        4. LLM invocation (contract-based)
        5. Clean output
        6. Write file
        7. Record experience in memory (pending human decision)
        """
        os.makedirs(target_dir, exist_ok=True)
        generated_files: list[str] = []

        ext = self._get_extension(spec.requirement.language.value)
        lang = spec.requirement.language.value
        project_name = spec.requirement.project_name
        requirement_desc = spec.requirement.description
        architecture = spec.architecture
        modules = spec.modules or [{"name": "main"}]

        for module in modules:
            module_name = module.get("name", "main")
            target_module = f"{project_name}/{module_name}"

            # Step 1: Privacy sanitization
            sanitized_req = self._sanitize(requirement_desc)
            sanitized_arch = self._sanitize(str(architecture))

            # §17 check performed by LLMClient → RestrictionGuard before calling generator
            # Rules: contracts/schemas/ai/restriction-rules-v1.json
            # Step 3: Build memory context
            memory_context = self._build_context(lang, target_module, sanitized_req)

            # Step 4: Build governed prompt
            repair_section = ""
            if repair_context:
                repair_section = (
                    "\nPREVIOUS ATTEMPT FAILED. Fix these errors:\n"
                    f"{self._sanitize(repair_context)}\n"
                )

            prompt_parts = [
                f"Generate a complete {lang} source file for module '{module_name}'.",
                f"Project: {project_name}",
                f"Requirement: {sanitized_req}",
                f"Architecture: {sanitized_arch}",
                f"All modules: {', '.join(m.get('name', '') for m in modules)}",
            ]
            if memory_context:
                prompt_parts.append(f"\n{memory_context}")
            if repair_section:
                prompt_parts.append(repair_section)
            rules = (
                "RULES: Production-grade only. Include error handling. "
                "No floats in financial calculations. "
                "Provide ONLY complete source code. No markdown, no explanations."
            )
            if lang == "go":
                rules += " Use ONLY Go standard library packages. Do NOT import external dependencies."
            prompt_parts.append(rules)

            prompt = "\n".join(prompt_parts)
            prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]

            # Step 5: LLM invocation (contract-based, with fallback)
            try:
                code_response = self.llm.generate_code(prompt, lang)
            except RuntimeError as e:
                logger.error("LLM call failed for %s: %s", module_name, e)
                raise

            clean_code = self._clean_code(code_response)

            # Step 6: Write file
            if ext == "rs":
                src_dir = os.path.join(target_dir, "src")
                os.makedirs(src_dir, exist_ok=True)
                file_path = os.path.join(src_dir, f"{module_name}.{ext}")
            else:
                file_path = os.path.join(target_dir, f"{module_name}.{ext}")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(clean_code.rstrip() + "\n")

            generated_files.append(os.path.relpath(file_path, target_dir))

            # Step 7: Record in memory (pending — human decides later)
            self.memory.record(
                source=Source(
                    provider="groq",
                    model=self.llm.model,
                    prompt_hash=prompt_hash,
                ),
                method=Method(
                    context_sources=[e.id for e in self.memory.get_positive(lang, target_module)],
                    temperature=0.2,
                ),
                artifact=MemArtifact(
                    language=lang,
                    module=target_module,
                    governance_refs=["llm-invocation-v1.json", "security-policy.yaml"],
                ),
                decision=Decision.APPROVED,  # Tentative — orchestrator updates after human gate
                reason="auto-generated, pending human review",
                quality_score=0.5,  # Neutral until human reviews
            )

            logger.info("Generated: %s (%d chars)", file_path, len(clean_code))

        # Go: Generate table-driven tests as second LLM call
        if lang == "go":
            for rel_path in generated_files:
                if rel_path.endswith(".go") and not rel_path.endswith("_test.go"):
                    abs_path = os.path.join(target_dir, rel_path)
                    with open(abs_path, "r") as f:
                        main_code = f.read()
                    test_prompt = (
                        "Generate ONLY Go table-driven tests for this code.\n"
                        "Same package. Use func TestXxx(t *testing.T) with []struct.\n"
                        "Cover success and error paths. Import only testing and time.\n"
                        "ONLY the test code. No markdown.\n\n"
                        "Source code:\n" + main_code
                    )
                    try:
                        test_code = self.llm.generate_code(test_prompt, "go")
                        test_file = rel_path.replace(".go", "_test.go")
                        test_abs = os.path.join(target_dir, test_file)
                        with open(test_abs, "w") as f:
                            f.write(test_code.rstrip() + "\n")
                        generated_files.append(test_file)
                        logger.info("Generated tests: %s", test_file)
                    except RuntimeError as e:
                        logger.warning("Go test generation failed: %s", e)

        # Go/Rust project manifests
        if lang == "go":
            go_mod_path = os.path.join(target_dir, "go.mod")
            if not os.path.exists(go_mod_path):
                with open(go_mod_path, "w", encoding="utf-8") as f:
                    f.write(f"module {project_name}\n\ngo 1.22\n")
            generated_files.append(os.path.relpath(go_mod_path, target_dir))

        if lang == "rust":
            cargo_toml_path = os.path.join(target_dir, "Cargo.toml")
            if not os.path.exists(cargo_toml_path):
                with open(cargo_toml_path, "w", encoding="utf-8") as f:
                    f.write(
                        f'[package]\nname = "{project_name}"\n'
                        f'version = "0.1.0"\nedition = "2021"\n'
                    )
            generated_files.append(os.path.relpath(cargo_toml_path, target_dir))

        return generated_files