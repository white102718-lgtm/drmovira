-- V22 仅识别旧版 SYSTEM 父菜单；统一菜单上线后父节点编码为 SystemManagement，
-- 导致申请管理的数据表已创建但导航菜单未写入。本迁移兼容两种父菜单编码并补齐管理员授权。
SET @system_management_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code IN ('SystemManagement', 'SYSTEM')
      AND status = 1
      AND deleted_at = 0
    ORDER BY CASE menu_code WHEN 'SystemManagement' THEN 0 ELSE 1 END
    LIMIT 1
);

SET @application_management_menu_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code IN ('SystemApplicationManagement', 'SYSTEM_APPLICATION')
      AND deleted_at = 0
    ORDER BY CASE menu_code WHEN 'SystemApplicationManagement' THEN 0 ELSE 1 END
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
    'SystemApplicationManagement',
    '申请管理',
    '/system-management/applications',
    '/system/application/list',
    'lucide:file-stack',
    'system:application:list',
    1,
    0,
    35,
    1,
    '管理申请入口及其审批配置关联'
WHERE @system_management_id IS NOT NULL
  AND @application_management_menu_id IS NULL;

SET @application_management_menu_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code IN ('SystemApplicationManagement', 'SYSTEM_APPLICATION')
      AND deleted_at = 0
    ORDER BY CASE menu_code WHEN 'SystemApplicationManagement' THEN 0 ELSE 1 END
    LIMIT 1
);

UPDATE sys_menu
SET parent_id = @system_management_id,
    menu_type = 2,
    menu_name = '申请管理',
    route_path = '/system-management/applications',
    component = '/system/application/list',
    icon = 'lucide:file-stack',
    permission_code = 'system:application:list',
    visible = 1,
    cacheable = 0,
    sort_order = 35,
    status = 1,
    remark = '管理申请入口及其审批配置关联'
WHERE id = @application_management_menu_id
  AND @system_management_id IS NOT NULL;

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, @application_management_menu_id
FROM sys_role role
WHERE role.role_code = 'ADMIN'
  AND role.status = 1
  AND role.deleted_at = 0
  AND @application_management_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_role_menu relation
      WHERE relation.role_id = role.id
        AND relation.menu_id = @application_management_menu_id
        AND relation.deleted_at = 0
  );
