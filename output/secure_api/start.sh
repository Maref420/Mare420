#!/bin/bash
# Production entrypoint — replaces fix_and_run.sh / run.sh
# Governed by: governance/policies/python-policy.yaml
set -euo pipefail

# Load secrets from secure location
if [ -f "configs/secure_api.env" ]; then
    set -a
    source configs/secure_api.env
    set +a
else
    echo "❌ Missing configs/secure_api.env — aborting"
    exit 1
fi

# Validate required env vars
: "${SECRET_KEY:?SECRET_KEY must be set}"
: "${DATABASE_URL:?DATABASE_URL must be set}"

echo "Starting secure_api with validated configuration..."
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --log-level info
