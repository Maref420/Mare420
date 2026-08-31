#!/bin/bash
set -euo pipefail

# ═══════════════════════════════════════════════════════
# INSPECT TARGET — Read-only inspection before destructive action
# Usage: bash scripts/inspect-target.sh <path>
# Output: Full inspection report to stdout (redirect to file for gate)
# ═══════════════════════════════════════════════════════

TARGET="${1:-}"

if [ -z "$TARGET" ]; then
  echo "❌ Usage: bash scripts/inspect-target.sh <path>"
  exit 1
fi

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║ INSPECTION REPORT: $TARGET"
echo "║ Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "╚═══════════════════════════════════════════════════════════╝"

echo ""
echo "=== 1. EXISTENCE CHECK ==="
if [ -e "$TARGET" ]; then
  echo "✅ EXISTS"
  ls -laR "$TARGET" 2>/dev/null || ls -la "$TARGET"
else
  echo "❌ DOES NOT EXIST"
fi

echo ""
echo "=== 2. GIT TRACKING STATUS ==="
git ls-files "$TARGET" 2>/dev/null || echo "(not tracked by git)"

echo ""
echo "=== 3. FILE CONTENTS ==="
if [ -d "$TARGET" ]; then
  find "$TARGET" -type f -exec sh -c 'echo "--- FILE: {} ---"; cat "{}" 2>/dev/null || echo "(binary/unreadable)"' \;
elif [ -f "$TARGET" ]; then
  echo "--- FILE: $TARGET ---"
  cat "$TARGET"
fi

echo ""
echo "=== 4. CROSS-PROJECT REFERENCES ==="
grep -rn "$(basename "$TARGET")" . \
  --include="*.yaml" --include="*.json" --include="*.toml" \
  --include="*.md" --include="*.py" --include="*.rs" --include="*.go" \
  --include="*.sh" --include="Makefile" \
  --exclude-dir=".git" --exclude-dir="target" --exclude-dir=".venv" \
  --exclude-dir="__pycache__" --exclude-dir="output/audit" \
  2>/dev/null || echo "(NO REFERENCES FOUND)"

echo ""
echo "=== 5. DECISION MATRIX ==="
echo "Review above output and decide:"
echo "  [PRESERVE]  — Unique logic not found elsewhere → migrate to correct module"
echo "  [DELETE]    — Ephemeral/duplicate/no references → safe to remove"
echo "  [DEPRECATE] — Still referenced but replaced → mark deprecated + timeline"
echo "  [UNKNOWN]   — Need more investigation → DO NOT PROCEED"
