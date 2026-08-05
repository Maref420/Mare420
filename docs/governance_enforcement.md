# Atlas AI Governance Enforcement

Version:
v0.1

Purpose:
Define enforcement rules for AI agents, developers, and system changes.

---

# Core Principle

Governance rules are mandatory.

No AI Agent or developer can bypass architecture decisions.

---

# Agent Workflow

Before generating code:

1. Read Governance documents.
2. Verify module ownership.
3. Verify contracts.
4. Verify schemas.
5. Check security requirements.

---

# Required Documents

Every Agent must review:

- governance/01_ARCHITECTURE_LOCK.md
- governance/02_MODULE_OWNERSHIP.md
- governance/03_AI_RULES.md
- docs/communication_architecture.md
- docs/security_architecture.md

---

# Architecture Change Rules

Forbidden:

- Creating new modules without approval.
- Changing module ownership.
- Bypassing contracts.
- Changing security boundaries.
- Mixing Rust Core and Python AI responsibilities.

---

# Contract Rules

All communication must use:

- Defined events
- Defined schemas
- Versioned contracts

Forbidden:

- Undocumented data exchange.
- Direct module dependency.

---

# Git Rules

Main branch:

- Contains approved architecture.
- No direct experimental changes.

Changes require:

1. Feature branch.
2. Review.
3. Validation.
4. Commit.

---

# AI Agent Restrictions

Agents must not:

- Modify locked governance files.
- Invent architecture.
- Add dependencies without approval.
- Remove security controls.
- Replace existing modules without validation.

---

# Change Approval

Architecture changes require:

- Documentation update.
- Impact analysis.
- Contract review.
- Security review.

---

Version:
v0.1
