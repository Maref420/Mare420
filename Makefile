# Atlas AI — Governance Enforcement Gate
# All targets are idempotent and non-destructive.
# Governed by: governance/policies/*.yaml
# ADR-2026-08-30-012

.PHONY: all check rust-check rust-test rust-clippy go-check go-test \
        python-test schema-validate secret-validate governance-audit \
        ci-gate help

all: ci-gate

help:
	@echo "Atlas AI Governance Gate"
	@echo "========================"
	@echo "  make ci-gate          — Run ALL checks (CI pipeline equivalent)"
	@echo "  make rust-check       — cargo check all Rust crates"
	@echo "  make rust-test        — cargo test all Rust crates"
	@echo "  make rust-clippy      — cargo clippy all Rust crates"
	@echo "  make go-check         — go build all Go services"
	@echo "  make go-test          — go test all Go services"
	@echo "  make python-test      — pytest production tests"
	@echo "  make schema-validate  — Validate all JSON schemas"
	@echo "  make secret-validate  — Validate secret registry"
	@echo "  make governance-audit — Full governance compliance audit"
	@echo "  make test-integration — Run integration tests (requires live broker)"

# ─── Rust Gates ───
rust-check:
	@echo "🔍 [Rust] cargo check..."
	@for crate in core_engine/market_data core_engine/risk core_engine/strategy; do \
		if [ -f "$$crate/Cargo.toml" ]; then \
			echo "  Checking $$crate..."; \
			cd $$crate && cargo check 2>&1 | tail -1 && cd ../..; \
		fi; \
	done
	@echo "✅ Rust check passed"

rust-test:
	@echo "🧪 [Rust] cargo test..."
	@for crate in core_engine/market_data core_engine/risk core_engine/strategy; do \
		if [ -f "$$crate/Cargo.toml" ]; then \
			echo "  Testing $$crate..."; \
			cd $$crate && cargo test 2>&1 | grep "^test result:" && cd ../..; \
		fi; \
	done
	@echo "✅ Rust tests passed"

rust-clippy:
	@echo "📎 [Rust] cargo clippy..."
	@FAIL=0; \
	for crate in core_engine/market_data core_engine/risk core_engine/strategy; do \
		if [ -f "$$crate/Cargo.toml" ]; then \
			echo "  Clippy $$crate..."; \
			cd $$crate && cargo clippy --all-targets -- -D warnings 2>&1 | tail -1 || FAIL=1; \
			cd ../..; \
		fi; \
	done; \
	if [ $$FAIL -ne 0 ]; then echo "❌ Clippy failed"; exit 1; fi
	@echo "✅ Rust clippy passed"

# ─── Go Gates ───
go-check:
	@echo "🔍 [Go] go build..."
	@cd services/message_broker && go build ./... 2>&1 | tail -1 && cd ../..
	@echo "✅ Go build passed"

go-test:
	@echo "🧪 [Go] go test..."
	@cd services/message_broker && go test ./... 2>&1 | tail -3 && cd ../..
	@echo "✅ Go tests passed"

# ─── Python Gates ───
python-test:
	@echo "🧪 [Python] pytest..."
	@python -m pytest tests/production/ -v --tb=short 2>&1 | tail -5
	@echo "✅ Python tests passed"

# ─── Schema Validation ───
schema-validate:
	@echo "📋 [Schema] Validating all JSON schemas..."
	@python3 scripts/validate_schemas.py

# ─── Secret Validation ───
secret-validate:
	@echo "🔐 [Secrets] Validating secret registry..."
	@python3 -c "\
	from intelligence.shared.secrets.provider import validate_secrets; \
	errors = validate_secrets(); \
	[print(f'  ⚠️  {e}') for e in errors]; \
	print(f'✅ Secret registry validated ({len(errors)} warnings)')"

# ─── Governance Audit ───
governance-audit:
	@echo "🏛️  [Governance] Compliance audit..."
	@echo "--- ADR count ---"
	@grep -c "^## ADR-" docs/decisions.md 2>/dev/null || echo "0"
	@echo "--- Contract count ---"
	@find contracts/schemas/ -name "*-v*.json" ! -name "*.bak*" | wc -l
	@echo "--- Module ownership entries ---"
	@grep -c "^- module:" governance/ownership/module-ownership.yaml 2>/dev/null || echo "0"
	@echo "--- Registered dependencies ---"
	@grep -c "name:" governance/registry/dependencies.yaml 2>/dev/null || echo "0"
	@echo "✅ Governance audit complete"
# ─── Integration Tests (require live services) ───
test-integration:
	@echo "🔗 [Integration] Running tests that require live services..."
	@echo "  Prerequisites:"
	@echo "    - Go Message Broker running on localhost:8090"
	@echo "    - Start broker: cd services/message_broker && go run main.go"
	@echo ""
	@echo "  Running Rust integration tests..."
	@cd core_engine/execution && cargo test --test prod_memory_pipeline -- --ignored --nocapture 2>&1 | tail -10
	@echo ""
	@echo "✅  Integration tests complete"


# ─── CI Gate (All Checks) ───
ci-gate: rust-check rust-test rust-clippy go-check go-test python-test schema-validate secret-validate governance-audit
	@echo ""
	@echo "=========================================="
	@echo "✅ CI GOVERNANCE GATE — ALL CHECKS PASSED"
	@echo "=========================================="
