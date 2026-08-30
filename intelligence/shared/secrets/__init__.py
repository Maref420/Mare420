"""Secret Provider Abstraction Layer.
Governed by: contracts/schemas/infrastructure/secret-provider-config-v1.json
ADR-2026-08-30-011
"""
from intelligence.shared.secrets.provider import get_secret, validate_secrets
__all__ = ["get_secret", "validate_secrets"]
