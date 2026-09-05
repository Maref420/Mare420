# ADR-002: Disposal of .bak Files in core_engine/market_data

## Status
Accepted | 2026-09-01

## Context
During P0-1 structural audit, two `.bak` files were discovered in
`core_engine/market_data/src/`:
- `types.rs.bak.pre-clippy-fix.1788102517`
- `types.rs.bak.pre-clippy-fix-v2.1788102702`

Initial concern: Files might contain unique logic requiring preservation
before deletion. Per Governance "No Silent Deletion" principle, investigation
was required before permanent removal.

## Investigation Results
1. `git restore` failed — files were **never committed** to Git
2. Timestamp naming pattern confirms auto-generated clippy backup artifacts
3. Zero references to these files anywhere in the codebase
4. All logic already present in current `types.rs` (post-clippy version)
5. Files existed only in working tree as ephemeral tool output

## Decision
Files correctly classified as **ephemeral tool artifacts**, not project assets.
Original deletion was correct and irreversible (no git history to restore from).

## Consequences
- ✅ Working tree clean, compliant with `security-policy.yaml` §artifact-lifecycle
- ✅ No logic lost (verified via investigation)
- ⚠️ Lesson learned: Always verify `git ls-files` tracking status before
  assuming recoverability of deleted files
- 🔒 Future prevention: `make validate-market-data` now includes `.bak` file check

## Related
- P0-1 Structural Audit Report
- `governance/policies/security-policy.yaml` §artifact-lifecycle
- `Makefile` target `validate-market-data`
