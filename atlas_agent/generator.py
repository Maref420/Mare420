import os
import re
from typing import Any

from .llm_client import LLMClient


class GeneratorEngine:
    def __init__(self) -> None:
        self.llm = LLMClient()

    def _clean_code(self, code: str) -> str:
        code = re.sub(r'^```python\s*', '', code, flags=re.MULTILINE)
        code = re.sub(r'^```\s*$', '', code, flags=re.MULTILINE)
        return code.strip()

    def generate_project(
        self,
        spec: Any,
        target_dir: str,
        repair_context: str | None = None,
    ) -> list[str]:
        """Generate project files per module in specification.

        Governed by: contracts/schemas/coding-loop/artifact-v1.json
        Each module produces an independent file. Repair context is
        applied globally to all modules when validation fails.
        """
        os.makedirs(target_dir, exist_ok=True)
        generated_files: list[str] = []
        ext = self._get_extension(spec.requirement.language.value)
        lang = spec.requirement.language.value
        project_name = spec.requirement.project_name
        requirement_desc = spec.requirement.description
        architecture = spec.architecture

        repair_section = ""
        if repair_context:
            repair_section = (
                "\nPrevious validation attempt failed.\n"
                "Repair the generated code based on these validation errors:\n"
                f"{repair_context}\n"
            )

        modules = spec.modules or [{"name": "main"}]

        for module in modules:
            module_name = module.get("name", "main")
            prompt = (
                f"Generate a complete {lang} source file for module '{module_name}'.\n"
                f"Project: {project_name}\n"
                f"Requirement: {requirement_desc}\n"
                f"Architecture: {architecture}\n"
                f"All modules: {', '.join(m.get('name', '') for m in modules)}\n"
                f"{repair_section}"
                f"Provide ONLY the complete source code for this single module. "
                f"No markdown, no filenames, no explanations."
            )

            try:
                code_response = self.llm.generate_code(prompt, lang)
                clean_code = self._clean_code(code_response)

                # Governed: Rust requires src/ directory structure for cargo tooling
                if ext == "rs":
                    src_dir = os.path.join(target_dir, "src")
                    os.makedirs(src_dir, exist_ok=True)
                    file_name = f"{module_name}.{ext}"
                    file_path = os.path.join(src_dir, file_name)
                else:
                    file_name = f"{module_name}.{ext}"
                    file_path = os.path.join(target_dir, file_name)

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(clean_code.rstrip() + "\n")

                # Governed: Return relative paths per artifact contract
                generated_files.append(os.path.relpath(file_path, target_dir))
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(
                    f"Code generation failed for module '{module_name}': {e!s}"
                ) from e

        # Go projects require go.mod at project root
        if lang == "go":
            go_mod_path = os.path.join(target_dir, "go.mod")
            if not os.path.exists(go_mod_path):
                with open(go_mod_path, "w", encoding="utf-8") as f:
                    f.write(f"module {project_name}\n\ngo 1.22\n")
            generated_files.append(os.path.relpath(go_mod_path, target_dir))

        # Rust projects require Cargo.toml at project root
        if lang == "rust":
            cargo_toml_path = os.path.join(target_dir, "Cargo.toml")
            if not os.path.exists(cargo_toml_path):
                with open(cargo_toml_path, "w", encoding="utf-8") as f:
                    f.write(f'[package]\nname = "{project_name}"\nversion = "0.1.0"\nedition = "2021"\n')
            generated_files.append(os.path.relpath(cargo_toml_path, target_dir))

        return generated_files

    def _get_extension(self, lang: str) -> str:
        extensions = {
            "python": "py",
            "rust": "rs",
            "go": "go"
        }
        return extensions.get(lang, "txt")
