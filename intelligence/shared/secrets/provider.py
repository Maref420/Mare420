"""Secret Provider — Environment Variable Backend.
Future backends: Vault, AWS Secrets Manager, GCP Secret Manager.
Governed by: contracts/schemas/infrastructure/secret-provider-config-v1.json
ADR-2026-08-30-011
"""
from __future__ import annotations
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Secret registry loaded once at module init
_REGISTRY_PATH = "configs/secret-registry.yaml"
_registry_cache: dict | None = None


def _load_registry() -> dict:
    """Load secret registry from YAML config."""
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache
    try:
        import yaml
        with open(_REGISTRY_PATH) as f:
            _registry_cache = yaml.safe_load(f)
    except Exception as exc:
        logger.error("Failed to load secret registry: %s", exc)
        _registry_cache = {"secrets": []}
    return _registry_cache


def get_secret(name: str) -> Optional[str]:
    """Retrieve a secret by logical name.
    Currently uses env var backend. Future: Vault/AWS/GCP.
    Returns None if not found and not required.
    Raises ValueError if required and missing.
    """
    registry = _load_registry()
    for entry in registry.get("secrets", []):
        if entry.get("name") == name:
            env_var = entry.get("env_var", "")
            value = os.environ.get(env_var)
            if value is None:
                if entry.get("required", False):
                    raise ValueError(
                        f"Required secret '{name}' ({env_var}) not set. "
                        f"Set via environment variable or secret manager."
                    )
                return None
            min_len = entry.get("min_length", 0)
            if len(value) < min_len:
                raise ValueError(
                    f"Secret '{name}' length {len(value)} < minimum {min_len}"
                )
            return value
    raise KeyError(f"Unknown secret name: '{name}'. Register in {_REGISTRY_PATH}")


def validate_secrets() -> list[str]:
    """Validate all required secrets are present and meet constraints.
    Returns list of error messages. Empty list = all valid.
    """
    errors: list[str] = []
    registry = _load_registry()
    for entry in registry.get("secrets", []):
        name = entry.get("name", "?")
        try:
            get_secret(name)
        except (ValueError, KeyError) as exc:
            errors.append(str(exc))
    return errors
