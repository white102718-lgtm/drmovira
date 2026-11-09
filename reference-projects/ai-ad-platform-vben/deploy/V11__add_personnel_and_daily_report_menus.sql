-- 为测试环境补齐“人员数据”和“日报配置”菜单（MySQL 8+）。
-- 人员数据沿用既有角色授权，仅迁移到“数据复盘”；日报配置仅授予 ADMIN。
START TRANSACTION;

SET @data_growth_center_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'DataGrowthCenter'
      AND status = 1
      AND deleted_at = 0
    LIMIT 1
);

SET @system_management_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'SystemManagement'
      AND status = 1
      AND deleted_at = 0
    LIMIT 1
);

-- 已存在的人员数据菜单可能来自旧版路由重建脚本，统一迁移到当前前端定义的“数据复盘”。
UPDATE sys_menu
SET parent_id = @data_growth_center_id,
    route_path = '/dashboard/personnel-data',
    component = '/dashboard/personnel-data',
    icon = 'lucide:users-round',
    visible = 1,
    cacheable = 0,
    sort_order = 18,
    status = 1,
    updated_at = CURRENT_TIMESTAMP(3)
WHERE menu_code = 'PersonnelData'
  AND deleted_at = 0
  AND @data_growth_center_id IS NOT NULL;

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
    @data_growth_center_id,
    2,
    'PersonnelData',
    '人员数据',
    '/dashboard/personnel-data',
    '/dashboard/personnel-data',
    'lucide:users-round',
    NULL,
    1,
    0,
    18,
    1,
    '按投放人员汇总消耗并支持层级下钻'
WHERE @data_growth_center_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'PersonnelData'
        AND deleted_at = 0
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
    'SystemDailyReportConfig',
    '日报配置',
    '/system-management/daily-report-config',
    '/system/daily-report-config',
    'lucide:table-properties',
    NULL,
    1,
    0,
    36,
    1,
    '配置日报字段、口径与展示顺序'
WHERE @system_management_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'SystemDailyReportConfig'
        AND deleted_at = 0
  );

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, menu.id
FROM sys_role role
INNER JOIN sys_menu menu
    ON menu.menu_code = 'SystemDailyReportConfig'
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

COMMIT;

SELECT menu_code, menu_name, parent_id, route_path, component, visible, sort_order
FROM sys_menu
WHERE menu_code IN ('PersonnelData', 'SystemDailyReportConfig')
  AND deleted_at = 0
ORDER BY menu_code;
