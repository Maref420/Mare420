import os

from dotenv import load_dotenv
from groq import Groq
from .llm_cache import LLMCache

load_dotenv()

class LLMClient:
    """
    LLM Client for external code generation.
    Enforces CONSTITUTION.md §17 restrictions on external AI usage:
    - Requires permission review before accepting credentials
    - Prevents generation of restricted code categories
    - Maintains audit trail of generation requests
    """
    # Restricted code patterns per CONSTITUTION.md §17
    RESTRICTED_CATEGORIES = {
        "hft_core": ["high-frequency", "HFT core", "millisecond execution", "latency-critical execution"],
        "execution_logic": ["order execution", "trade execution", "execution engine", "exchange order"],
        "risk_systems": ["risk engine", "risk management", "position limits", "exposure control"],
        "trading_strategies": ["trading strategy", "strategy logic", "signal generation", "backtest"],
    }
    def __init__(self) -> None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing in .env file")
        self.client = Groq(api_key=api_key)
        self._cache = LLMCache()
        self.model = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
        self.fallback_model = os.getenv("LLM_FALLBACK_MODEL", "openai/gpt-oss-20b")

    def _check_restricted_content(self, requirement: str) -> str | None:
        """
        Check if requirement requests restricted code generation.
        
        Returns category name if restricted, None if allowed.
        Implements CONSTITUTION.md §17 restrictions.
        """
        requirement_lower = requirement.lower()
        
        for category, patterns in self.RESTRICTED_CATEGORIES.items():
            for pattern in patterns:
                if pattern.lower() in requirement_lower:
                    return category
        
        return None

    def generate_code(self, requirement: str, language: str) -> str:
        """
        Generate code for the given requirement and language.
        
        Enforces CONSTITUTION.md §17 restrictions on external AI code generation.
        
        Raises:
            ValueError: If requirement requests restricted code categories
            RuntimeError: If LLM API call fails
        """
        restricted_category = self._check_restricted_content(requirement)
        if restricted_category:
            raise ValueError(
                f"Code generation rejected: requirement matches restricted category '{restricted_category}'. "
                f"CONSTITUTION.md §17 prohibits external AI from generating: "
                f"HFT core, execution logic, risk systems, trading strategies."
            )
        
        prompt = f"""
        You are a senior software engineer.
        Generate professional, secure, and efficient {language} code for the following requirement:

        {requirement}

        Ensure the code follows best practices, includes error handling, and is production-ready.
        """
        # Check cache first
        cached = self._cache.get(prompt, self.model, 0.2)
        if cached is not None:
            self._circuit_breaker.record_success()
            return cached

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2048
            )
            content = response.choices[0].message.content
            if content is None:
                raise RuntimeError("LLM returned empty content")
            return content
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"LLM Generation Failed: {e!s}") from e

    def analyze_security(self, code: str) -> str:
        """
        Analyze code for security vulnerabilities.
        
        Raises:
            RuntimeError: If security analysis fails
        """
        prompt = f"""
        Review the following code for security vulnerabilities (SQL Injection, XSS, Hardcoded Secrets).
        Provide a concise report of any issues found.

        {code}
        """
        # Check cache first
        cached = self._cache.get(prompt, self.model, 0.2)
        if cached is not None:
            self._circuit_breaker.record_success()
            return cached

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            content = response.choices[0].message.content
            if content is None:
                raise RuntimeError("LLM security analysis returned empty content")
            return content
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Security analysis failed: {e!s}") from e
