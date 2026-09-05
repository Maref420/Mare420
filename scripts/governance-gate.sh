#!/bin/bash
set -euo pipefail

# ═══════════════════════════════════════════════════════
# GOVERNANCE GATE — Mechanical enforcement of inspection-before-action
# Usage: bash scripts/governance-gate.sh <action> <target>
# Actions: delete, modify, create
# ═══════════════════════════════════════════════════════

ACTION="${1:-}"
TARGET="${2:-}"

if [ -z "$ACTION" ] || [ -z "$TARGET" ]; then
  echo "❌ Usage: bash scripts/governance-gate.sh <delete|modify|create> <path>"
  exit 1
fi

AUDIT_DIR="output/audit"
mkdir -p "$AUDIT_DIR"
SAFE_TARGET=$(echo "$TARGET" | tr '/' '_')
INSPECTION_FILE="$AUDIT_DIR/${SAFE_TARGET}_inspection.txt"

case "$ACTION" in
  delete)
    if [ ! -f "$INSPECTION_FILE" ]; then
      echo "⛔ BLOCKED: No inspection report for '$TARGET'"
      echo "   Required: Run inspection FIRST, then re-run this gate."
      echo "   Inspection command:"
      echo "     bash scripts/inspect-target.sh $TARGET > $INSPECTION_FILE"
      echo "   Then review output and re-run: bash scripts/governance-gate.sh delete $TARGET"
      exit 1
    fi
    echo "✅ Inspection verified for: $TARGET"
    echo "   Proceeding with deletion..."
    rm -rf "$TARGET"
    echo "✅ Deleted: $TARGET"
    ;;
  modify)
    echo "✅ Modify gate passed for: $TARGET"
    echo "   Reminder: Ensure README + contract updated in same change."
    ;;
  create)
    echo "✅ Create gate passed for: $TARGET"
    echo "   Reminder: Add Governance header + register in artifact-ownership.yaml"
    ;;
  *)
    echo "❌ Unknown action: $ACTION (use: delete, modify, create)"
    exit 1
    ;;
esac
