import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

class LLMClient:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing in .env file")
        self.client = Groq(api_key=api_key)
        self.model = "openai/gpt-oss-120b"

    def generate_code(self, requirement: str, language: str) -> str:
        prompt = f"""
        You are a senior software engineer.
        Generate professional, secure, and efficient {language} code for the following requirement:
        
        {requirement}
        
        Ensure the code follows best practices, includes error handling, and is production-ready.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2048
            )
            return response.choices[0].message.content
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"LLM Generation Failed: {e!s}")

    def analyze_security(self, code: str) -> str:
        prompt = f"""
        Review the following code for security vulnerabilities (SQL Injection, XSS, Hardcoded Secrets).
        Provide a concise report of any issues found.
        
        {code}
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return response.choices[0].message.content
