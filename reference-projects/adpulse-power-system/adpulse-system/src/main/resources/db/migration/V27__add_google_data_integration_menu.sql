SET @system_management_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code IN ('SystemManagement', 'SYSTEM')
      AND status = 1
      AND deleted_at = 0
    ORDER BY CASE menu_code WHEN 'SystemManagement' THEN 0 ELSE 1 END
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
    'SystemDataIntegration',
    'Google数据集成',
    '/system-management/data-integration',
    '/media-resources/data-integration',
    'lucide:plug-zap',
    'system:data-integration:manage',
    1,
    0,
    47,
    1,
    'Google账号授权、报表映射与数据同步配置入口'
WHERE @system_management_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'SystemDataIntegration'
        AND deleted_at = 0
  );

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, menu.id
FROM sys_role role
INNER JOIN sys_menu menu
    ON menu.menu_code = 'SystemDataIntegration'
   AND menu.status = 1
   AND menu.deleted_at = 0
WHERE role.role_code = 'ADMIN'
  AND role.status = 1
  AND role.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1
      FROM sys_role_menu relation
      WHERE relation.role_id = role.id
        AND relation.menu_id = menu.id
        AND relation.deleted_at = 0
  );
