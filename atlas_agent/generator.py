import os
import re
from typing import List, Dict, Any
from .llm_client import LLMClient

class GeneratorEngine:
    def __init__(self):
        self.llm = LLMClient()

    def _clean_code(self, code: str) -> str:
        code = re.sub(r'^```python\s*', '', code, flags=re.MULTILINE)
        code = re.sub(r'^```\s*$', '', code, flags=re.MULTILINE)
        return code.strip()

    def generate_project(self, spec: Any, target_dir: str) -> List[str]:
        os.makedirs(target_dir, exist_ok=True)
        generated_files = []

        lang = spec.requirement.language.value
        project_name = spec.requirement.project_name
        requirement = spec.requirement.description
        architecture = spec.architecture

        prompt = f"""
        Generate a complete {lang} project for: {requirement}
        Project Name: {project_name}
        Architecture: {architecture}
        Modules: {', '.join([m.get('name', '') for m in spec.modules])}

        Provide ONLY the raw code without markdown formatting or explanations.
        """

        try:
            code_response = self.llm.generate_code(prompt, lang)
            clean_code = self._clean_code(code_response)
            
            main_file = f"main.{self._get_extension(lang)}"
            main_path = os.path.join(target_dir, main_file)
            with open(main_path, "w") as f:
                f.write(clean_code)
            generated_files.append(main_path)
        except Exception as e:
            raise RuntimeError(f"Code generation failed: {str(e)}")

        return generated_files

    def _get_extension(self, lang: str) -> str:
        extensions = {
            "python": "py",
            "rust": "rs",
            "go": "go"
        }
        return extensions.get(lang, "txt")
