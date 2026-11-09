---
name: adpulse-system-backend
description: Maintain and extend the AdPulse Spring Boot system-management backend. Use when implementing, reviewing, debugging, or designing authentication, users, roles, departments, menus, MyBatis mappers, Redis-backed JWT sessions, manually executed database scripts, or related tests in adpulse-system-server.
---

# AdPulse system backend

1. Read `references/architecture.md` before changing application structure, security, sessions, or module boundaries.
2. Read `references/database.md` before changing entities, mappers, SQL, migrations, uniqueness, or deletion behavior.
3. Preserve the API/domain split: controller adapts HTTP, service owns transactions and invariants, mapper owns persistence.
4. Run `mvn spotless:apply` after Java edits and `mvn verify` before handoff when Maven is available.
5. Add or update tests for authorization, reference validation, tree movement, session revocation, or soft-delete behavior.
6. Keep Javadoc concise and explain business intent. Never add comments that merely restate syntax.
