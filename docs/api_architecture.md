# Atlas AI API Architecture

Version:
v0.1

Purpose:
Define API boundaries and communication rules.

---

## API Principle

All external communication must pass through controlled interfaces.

Direct module access is forbidden.

---

## API Layers

Interface Layer:
Responsible for user interaction.

API Gateway:
Responsible for routing, authentication, and authorization.

Core API:
Responsible for Rust Core operations.

AI API:
Responsible for AI analysis and recommendations.

---

## Request Flow

User
 |
 v
Interface
 |
 v
API Gateway
 |
 +--> Rust Core API
 |
 +--> Python AI API

---

## Forbidden

- Direct database access from API clients
- Direct exchange access from Interface
- AI executing trades
- API bypassing security controls

---

## Security Requirements

- Authentication required
- Authorization required
- Request validation
- Audit logging

---

Version:
v0.1
