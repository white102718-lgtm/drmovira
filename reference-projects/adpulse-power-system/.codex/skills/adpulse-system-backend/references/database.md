# Database reference

## Global rules

- Do not declare foreign keys.
- Use `BIGINT UNSIGNED AUTO_INCREMENT` primary keys.
- Use `deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0` on business and relation tables.
- `deleted_at = 0` means active; deletion writes Unix epoch milliseconds.
- Include `deleted_at` in business unique indexes so identifiers can be reused after deletion.
- Validate referenced active rows in service code before writes.
- Keep indexes on all logical relation columns.

## Relations

- `sys_user.primary_department_id` is the user's single home department.
- `sys_user_department_scope` grants data access and can include descendants.
- `sys_user_role` assigns roles; `sys_role_menu` assigns menu permissions.
- `sys_ip_rule.scope_type=1` is global and requires null `user_id`; type 2 is user-specific.
- `sys_menu` models directory, menu, and button resources as an adjacency tree.
- Current-user navigation must traverse only active user-role-menu relations and include active ancestors of assigned nodes.

## MFA

- `sys_user.mfa_status=-1` disables MFA, `0` requires initial binding, and `1` requires TOTP verification.
- Do not recreate or reference the retired `sys_user.mfa_enabled` column.
- Protect the MFA secret ciphertext and retain `mfa_last_used_counter` to reject TOTP replay.

## Login audit

- `sys_login_log` is append-only audit data and does not use soft deletion.
- Record final authentication successes and failures; do not classify an MFA challenge as a successful login.
- Never store passwords, access tokens, challenge tokens, MFA secrets, or TOTP codes in login logs.

## Operation audit

- `sys_operation_log` is append-only audit data and does not use soft deletion.
- Record all system-management create, update, delete, password reset, and MFA reset outcomes.
- Do not store request bodies or any password, token, MFA secret, or dynamic code.

## Deletion

- Reject department deletion when active children, users, or scopes reference it.
- Reject role deletion while active user-role relations reference it.
- Reject menu deletion while active children reference it; remove role-menu relations in the same transaction when allowed.
- Soft-delete dependent user relations and revoke sessions when deleting a user.
