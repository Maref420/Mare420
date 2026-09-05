"""Validate all JSON schemas under contracts/schemas/."""
import json
import sys
from pathlib import Path

errors = []
count = 0
for f in sorted(Path("contracts/schemas").rglob("*.json")):
    if ".bak" in str(f):
        continue
    count += 1
    try:
        json.loads(f.read_text())
    except Exception as e:
        errors.append(f"{f}: {e}")

if errors:
    print("❌ Schema validation failed:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)

print(f"✅ All {count} schemas valid")
