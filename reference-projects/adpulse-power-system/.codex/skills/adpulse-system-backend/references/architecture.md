# Architecture reference

## Stack

Java 21, Spring Boot 3.5, Spring Security, MyBatis XML, MySQL 8, Redis, JJWT and Maven. Database scripts are reviewed and executed manually before application deployment; the application does not migrate schemas at startup.

## Module rules

- Package by domain: `auth`, `loginlog`, `operationlog`, `user`, `role`, `department`, `menu`.
- Keep DTOs at the HTTP boundary. Do not expose persistence models directly.
- Put cross-domain orchestration in services and protect multi-table writes with transactions.
- Do not inject one controller into another or call mappers across controllers.
- Return IDs as JSON strings.

## API response codes

- Every JSON business code must be a three-digit constant declared in `ApiCode`; never add numeric literals in controllers or services.
- Use `2xx` for success, `4xx` for frontend flow errors that suppress global messages, `5xx` for business errors whose message may be shown to users, and `6xx` for silent system failures.
- Every application response handled by Spring MVC or Spring Security uses HTTP 200; clients determine success and error handling exclusively from the JSON business code.
- Update `docs/API_RESPONSE_CODE.md` whenever a response code is added or its semantics change.

## Authentication

- JWT contains the session ID (`sid`) and user ID (`sub`).
- Redis key `adpulse:session:{sid}` is authoritative. A valid JWT without the Redis session is rejected.
- Revoke all user sessions after password changes, disabling, or soft deletion.
- Store only password hashes. Use BCrypt.
- Apply IP access policy before creating a session and on authenticated requests.
- Persist final login successes and authentication failures without passwords, tokens, MFA secrets, or dynamic codes.
- `GET /menus` resolves the current user's active role menus from the database and returns Vben-compatible navigation routes without button nodes.

## CORS

- The current integration phase allows every origin, HTTP method, and request header without cross-origin credentials.
- CORS only relaxes browser origin checks; JWT, Redis session, IP policy, and method permissions remain mandatory.
- Replace the wildcard origin policy with an environment-specific allowlist before the public production rollout.

## Operation audit

- Every system-management create, update, delete, password reset, or MFA reset endpoint must declare `@OperationAudit`.
- Keep successful business writes and their operation-log insert in one database transaction.
- Never serialize request bodies into audit logs; metadata must not contain passwords, tokens, MFA secrets, or dynamic codes.

## Quality

- Public classes and public business methods require Chinese Javadoc.
- Use constructor injection.
- Use `@Transactional` only at service boundaries.
- Keep mapper XML SQL formatted with one selected column or predicate group per line when long.
- Never swallow exceptions or return success after a failed write.
