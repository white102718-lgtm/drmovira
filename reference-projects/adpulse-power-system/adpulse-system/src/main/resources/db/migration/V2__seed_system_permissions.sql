INSERT INTO sys_role (role_code, role_name, status, sort_order, remark)
VALUES ('ADMIN', '系统管理员', 1, 0, '系统内置管理员角色');

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, permission_code, sort_order, status
) VALUES
    (0, 1, 'SYSTEM', '系统管理', NULL, 10, 1);

SET @system_menu_id = LAST_INSERT_ID();

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    permission_code, sort_order, status
) VALUES
    (@system_menu_id, 2, 'SYSTEM_USER', '用户管理', '/system/user',
        'system/user/list', 'system:user:list', 10, 1),
    (@system_menu_id, 2, 'SYSTEM_ROLE', '角色管理', '/system/role',
        'system/role/list', 'system:role:list', 20, 1),
    (@system_menu_id, 2, 'SYSTEM_DEPARTMENT', '部门管理', '/system/department',
        'system/department/list', 'system:department:list', 30, 1),
    (@system_menu_id, 2, 'SYSTEM_MENU', '菜单管理', '/system/menu',
        'system/menu/list', 'system:menu:list', 40, 1);

SET @user_menu_id = (SELECT id FROM sys_menu WHERE menu_code = 'SYSTEM_USER' AND deleted_at = 0);
SET @role_menu_id = (SELECT id FROM sys_menu WHERE menu_code = 'SYSTEM_ROLE' AND deleted_at = 0);
SET @department_menu_id = (SELECT id FROM sys_menu WHERE menu_code = 'SYSTEM_DEPARTMENT' AND deleted_at = 0);
SET @menu_menu_id = (SELECT id FROM sys_menu WHERE menu_code = 'SYSTEM_MENU' AND deleted_at = 0);

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, permission_code, sort_order, status
) VALUES
    (@user_menu_id, 3, 'SYSTEM_USER_CREATE', '新增用户', 'system:user:create', 10, 1),
    (@user_menu_id, 3, 'SYSTEM_USER_UPDATE', '修改用户', 'system:user:update', 20, 1),
    (@user_menu_id, 3, 'SYSTEM_USER_DELETE', '删除用户', 'system:user:delete', 30, 1),
    (@user_menu_id, 3, 'SYSTEM_USER_RESET_PASSWORD', '重置密码', 'system:user:reset-password', 40, 1),
    (@user_menu_id, 3, 'SYSTEM_USER_RESET_MFA', '重置MFA', 'system:user:reset-mfa', 50, 1),
    (@user_menu_id, 3, 'SYSTEM_IP_LIST', '查看通用IP', 'system:ip:list', 60, 1),
    (@user_menu_id, 3, 'SYSTEM_IP_CREATE', '新增通用IP', 'system:ip:create', 70, 1),
    (@user_menu_id, 3, 'SYSTEM_IP_UPDATE', '修改通用IP', 'system:ip:update', 80, 1),
    (@user_menu_id, 3, 'SYSTEM_IP_DELETE', '删除通用IP', 'system:ip:delete', 90, 1),
    (@role_menu_id, 3, 'SYSTEM_ROLE_CREATE', '新增角色', 'system:role:create', 10, 1),
    (@role_menu_id, 3, 'SYSTEM_ROLE_UPDATE', '修改角色', 'system:role:update', 20, 1),
    (@role_menu_id, 3, 'SYSTEM_ROLE_DELETE', '删除角色', 'system:role:delete', 30, 1),
    (@department_menu_id, 3, 'SYSTEM_DEPARTMENT_CREATE', '新增部门', 'system:department:create', 10, 1),
    (@department_menu_id, 3, 'SYSTEM_DEPARTMENT_UPDATE', '修改部门', 'system:department:update', 20, 1),
    (@department_menu_id, 3, 'SYSTEM_DEPARTMENT_DELETE', '删除部门', 'system:department:delete', 30, 1),
    (@menu_menu_id, 3, 'SYSTEM_MENU_CREATE', '新增菜单', 'system:menu:create', 10, 1),
    (@menu_menu_id, 3, 'SYSTEM_MENU_UPDATE', '修改菜单', 'system:menu:update', 20, 1),
    (@menu_menu_id, 3, 'SYSTEM_MENU_DELETE', '删除菜单', 'system:menu:delete', 30, 1);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT r.id, m.id
FROM sys_role r
CROSS JOIN sys_menu m
WHERE r.role_code = 'ADMIN'
  AND r.deleted_at = 0
  AND m.deleted_at = 0;
