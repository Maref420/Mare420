# Governance Record

## Change ID
CR-MKT-DATA-P0-004

## Title
Lessons Learned: P1 Scaffold Implementation Pitfalls

## Status
Accepted

## Summary
Three preventable errors occurred during P1 scaffold implementation due to
assumptions made without verification. This record documents each failure,
root cause, and mandatory preventive measure for all future work.

## Incidents

### 1. SerializeFrame inaccessible from production code
- Symptom: `undefined: SerializeFrame` compile error in writer.go
- Root Cause: Function was defined in cross_validation_test.go (test file).
  Go test files are NOT visible to non-test compilation units.
- Assumption Made: "Test helper functions are available package-wide"
- Fix: Extracted to frame.go as production code
- Prevention: NEVER define shared utility functions in _test.go files.
  If a function is called by both test and production code, it MUST live
  in a non-test .go file. Verify with `go build ./...` BEFORE presenting.

### 2. Missing fmt import in client_test.go
- Symptom: `undefined: fmt` compile error
- Root Cause: Test file used fmt.Errorf but import block did not include "fmt"
- Assumption Made: "Import block is complete because I wrote it"
- Fix: Added "fmt" to import block
- Prevention: After generating ANY Go file, run `go vet` on that package
  BEFORE presenting to user. Never assume imports are correct.

### 3. WebSocket library not in go.mod
- Symptom: Build worked initially (no WS code), then failed after adding
  nhooyr.io/websocket usage without running go get first
- Root Cause: Presented client.go using websocket.Dial before ensuring
  dependency was installed
- Assumption Made: "Library is available because I referenced it"
- Fix: Ran `go get nhooyr.io/websocket@latest` separately
- Prevention: Before writing code that uses ANY external dependency,
  verify it exists in go.mod FIRST. If missing, install BEFORE writing
  the consuming code. Order: go get -> write code -> go build -> present.

## Mandatory Pre-Presentation Checklist (All Future Work)
Before presenting ANY code to user, verify:
1. `go build ./...` passes (catches undefined symbols, missing imports)
2. `go vet ./...` passes (catches unused imports, suspicious constructs)
3. All external dependencies exist in go.mod BEFORE writing consuming code
4. Shared functions live in non-test files
5. NEVER assume; ALWAYS verify with tool output

## Behavioral Correction
- Assistant MUST NOT present "OK" or checkmark without reading full tool output
- Assistant MUST run build/vet BEFORE presenting generated code
- Assistant MUST state uncertainty explicitly when verification is incomplete
- User authority is absolute; corrections must be accepted immediately

## Related
- ADR-006: WebSocket Ingestion Architecture
- ADR-007: Market Data Lifecycle Policy
- CR-MKT-DATA-P0-002: WebSocket Ingestion Scaffold
- Commit: 8fb4b1a (P1 scaffold complete)

## Applicability
This checklist applies to ALL future phases (P1-Final, P2-P6) and ALL
languages (Go, Rust, Python). No exceptions.

### G. Governance
- G1. ADR reference in code comments
- G2. README updated if module scope changed
- G3. No parallel paths created
- G4. No governance rules modified without new ADR

### H. Data Lifecycle Traceability (Production-Grade Business Requirement)
- H1. Every raw frame receives unique trace_id at INGEST stage (Go adapter)
- H2. trace_id propagated through ALL lifecycle stages:
      INGEST → VALIDATE → NORMALIZE → DISTRIBUTE → CONSUME | STORE | ARCHIVE
- H3. trace_id included in:
      - IPC binary header (ipc-binary-v1 spec amendment)
      - Rust NormalizedTick struct
      - All lifecycle_ metrics as label
      - Structured logs at every stage
      - Quarantine/purge audit records
- H4. End-to-end trace verification test exists:
      Inject known frame → verify trace_id appears at CONSUME/STORE output
- H5. trace_id format: {exchange}-{timestamp_ms}-{sequence}
      (sortable, debuggable, no external dependency)
- H6. Sampling strategy defined for high-throughput scenarios
      (e.g., 1% full trace, 100% trace_id propagation)
- H7. Compliance query interface specified:
      Given trace_id → retrieve all lifecycle events across all stages
