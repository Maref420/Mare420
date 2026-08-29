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
        os.makedirs(target_dir, exist_ok=True)
        generated_files = []

        lang = spec.requirement.language.value
        project_name = spec.requirement.project_name
        requirement = spec.requirement.description
        architecture = spec.architecture

        repair_section = ""
        if repair_context:
            repair_section = f"""
Previous validation attempt failed.
Repair the generated code based on these validation errors:
{repair_context}
"""

        prompt = f"""
        Generate a complete {lang} project for: {requirement}
        Project Name: {project_name}
        Architecture: {architecture}
        Modules: {', '.join([m.get('name', '') for m in spec.modules])}
        {repair_section}
        Provide ONLY the complete contents of main source file. Do not include go.mod, other files, markdown, filenames, or explanations. The generated main source must be self-contained.
        """


        try:
            code_response = self.llm.generate_code(prompt, lang)
            clean_code = self._clean_code(code_response)

            main_file = f"main.{self._get_extension(lang)}"
            main_path = os.path.join(target_dir, main_file)

            with open(main_path, "w", encoding="utf-8") as f:
                f.write(clean_code.rstrip() + "\n")

            generated_files.append(main_path)

            if lang == "go":
                go_mod_path = os.path.join(target_dir, "go.mod")
                with open(go_mod_path, "w", encoding="utf-8") as f:
                    f.write(f"module {project_name}\n\ngo 1.22\n")
                generated_files.append(go_mod_path)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Code generation failed: {e!s}") from e

        return generated_files

    def _get_extension(self, lang: str) -> str:
        extensions = {
            "python": "py",
            "rust": "rs",
            "go": "go"
        }
        return extensions.get(lang, "txt")
