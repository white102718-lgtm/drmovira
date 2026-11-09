-- 为已执行 V7 菜单重建脚本的环境增量补充部门管理（MySQL 8+）。
-- 新环境仍按顺序执行 V7、V8；旧版 SYSTEM 菜单已自带部门管理，无需执行本脚本。

START TRANSACTION;

SET @system_management_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'SystemManagement'
      AND status = 1
      AND deleted_at = 0
    LIMIT 1
);

INSERT INTO sys_menu (
    parent_id,
    menu_type,
    menu_code,
    menu_name,
    route_path,
    component,
    icon,
    permission_code,
    visible,
    cacheable,
    sort_order,
    status,
    remark
)
SELECT
    @system_management_id,
    2,
    'SystemDepartments',
    '部门管理',
    '/system-management/departments',
    '/system/department/list',
    'lucide:building-2',
    'system:department:list',
    1,
    0,
    20,
    1,
    NULL
WHERE @system_management_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'SystemDepartments'
        AND deleted_at = 0
  );

-- 先只补充页面级菜单权限，按钮权限后续统一处理。
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT r.id, m.id
FROM sys_role r
INNER JOIN sys_menu m
    ON m.menu_code = 'SystemDepartments'
   AND m.status = 1
   AND m.deleted_at = 0
WHERE r.role_code = 'ADMIN'
  AND r.status = 1
  AND r.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1
      FROM sys_role_menu rm
      WHERE rm.role_id = r.id
        AND rm.menu_id = m.id
        AND rm.deleted_at = 0
  );

-- 保持系统管理子菜单顺序一致。
UPDATE sys_menu
SET sort_order = CASE menu_code
        WHEN 'SystemDepartments' THEN 20
        WHEN 'SystemRoles' THEN 30
        WHEN 'SystemMenus' THEN 40
        WHEN 'AdgenOperations' THEN 50
        ELSE sort_order
    END,
    updated_at = CURRENT_TIMESTAMP(3)
WHERE parent_id = @system_management_id
  AND menu_code IN (
      'SystemDepartments',
      'SystemRoles',
      'SystemMenus',
      'AdgenOperations'
  )
  AND deleted_at = 0;

COMMIT;

SELECT menu_code, menu_name, route_path, component, permission_code, sort_order
FROM sys_menu
WHERE menu_code = 'SystemDepartments'
  AND status = 1
  AND deleted_at = 0
ORDER BY menu_type, sort_order;
