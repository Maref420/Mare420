#!/bin/bash
# Production entrypoint — Governed by governance/policies/python-policy.yaml
# Secret loading: configs/secret-registry.yaml (ADR-2026-08-30-011)
set -euo pipefail

# Load secrets from env file if present (backward compatible)
if [ -f "configs/secure_api.env" ]; then
    set -a
    source configs/secure_api.env
    set +a
fi

# Validate required secrets via Python provider
VALIDATION_ERRORS=$(python3 -c "
from intelligence.shared.secrets.provider import validate_secrets
errors = validate_secrets()
for e in errors:
    print(e)
" 2>&1) || true

if [ -n "$VALIDATION_ERRORS" ]; then
    echo "❌ Secret validation failed:"
    echo "$VALIDATION_ERRORS"
    exit 1
fi

echo "✅ All secrets validated successfully"
echo "Starting secure_api..."
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --log-level info
