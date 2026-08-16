from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ATLAS AI Agent"
    version: str = "1.0.0"
    debug: bool = False

    base_dir: str = "/root/Atlas-AI"
    temp_dir: str = "/tmp/atlas_agent"
    logs_dir: str = "/root/Atlas-AI/logs"
    artifacts_dir: str = "/root/Atlas-AI/artifacts"

    governance_enabled: bool = True
    fail_closed: bool = True
    require_human_approval: bool = True

    secret_patterns: List[str] = [
        r'api_key\s*=\s*["\']',
        r'password\s*=\s*["\']',
        r'secret\s*=\s*["\']',
    ]
    allowed_languages: List[str] = ["python", "rust", "go"]

    sandbox_timeout: int = 30
    sandbox_memory_limit: int = 512

    groq_api_key: Optional[str] = None

settings = Settings()
