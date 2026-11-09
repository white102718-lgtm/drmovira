-- 将本次新增的供应链管理、项目日报注册到菜单管理（MySQL 8+）。
-- 仅授予 ADMIN；其他角色请在“菜单管理 / 角色权限”中按业务范围授权。
START TRANSACTION;

SET @data_growth_center_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'DataGrowthCenter'
      AND status = 1
      AND deleted_at = 0
    LIMIT 1
);

SET @media_resource_center_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'MediaResourceCenter'
      AND status = 1
      AND deleted_at = 0
    LIMIT 1
);

-- 已有同编码菜单时统一修正其父级、前端组件和排序，保证脚本可重复执行。
UPDATE sys_menu
SET parent_id = @data_growth_center_id,
    menu_type = 2,
    menu_name = '项目日报',
    route_path = '/dashboard/project-daily-report',
    component = '/dashboard/project-daily-report',
    icon = 'lucide:calendar-range',
    visible = 1,
    cacheable = 0,
    sort_order = 12,
    status = 1,
    updated_at = CURRENT_TIMESTAMP(3)
WHERE menu_code = 'ProjectDailyReport'
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
    'ProjectDailyReport',
    '项目日报',
    '/dashboard/project-daily-report',
    '/dashboard/project-daily-report',
    'lucide:calendar-range',
    NULL,
    1,
    0,
    12,
    1,
    '按项目和代理线汇总每日消耗、充值、提现与留存数据'
WHERE @data_growth_center_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'ProjectDailyReport'
        AND deleted_at = 0
  );

UPDATE sys_menu
SET parent_id = @media_resource_center_id,
    menu_type = 2,
    menu_name = '供应链管理',
    route_path = '/media-resources/supply-chain',
    component = '/media-resources/supply-chain',
    icon = 'lucide:handshake',
    visible = 1,
    cacheable = 0,
    sort_order = 25,
    status = 1,
    updated_at = CURRENT_TIMESTAMP(3)
WHERE menu_code = 'MediaResourceSupplyChain'
  AND deleted_at = 0
  AND @media_resource_center_id IS NOT NULL;

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
    @media_resource_center_id,
    2,
    'MediaResourceSupplyChain',
    '供应链管理',
    '/media-resources/supply-chain',
    '/media-resources/supply-chain',
    'lucide:handshake',
    NULL,
    1,
    0,
    25,
    1,
    '维护合作客户群、政策、在线表与合作状态'
WHERE @media_resource_center_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'MediaResourceSupplyChain'
        AND deleted_at = 0
  );

-- 菜单默认仅对管理员可见，后续由角色管理按需分配。
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, menu.id
FROM sys_role role
INNER JOIN sys_menu menu
    ON menu.menu_code IN ('MediaResourceSupplyChain', 'ProjectDailyReport')
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

SELECT menu_code, menu_name, parent_id, route_path, component, icon, sort_order
FROM sys_menu
WHERE menu_code IN ('MediaResourceSupplyChain', 'ProjectDailyReport')
  AND deleted_at = 0
ORDER BY menu_code;
