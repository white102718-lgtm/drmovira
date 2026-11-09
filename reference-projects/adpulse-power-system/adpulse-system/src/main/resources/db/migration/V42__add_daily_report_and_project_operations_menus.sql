-- 日报中心与项目运营面板统一由 sys_menu 下发，避免前端兜底路由绕过角色菜单授权。
-- 隐藏日报页面挂在日报中心下，前端注册时会平铺为独立路由并沿用日报中心的 activePath。
START TRANSACTION;

SET @workbench_center_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'WorkbenchCenter'
      AND deleted_at = 0
    LIMIT 1
);

SET @data_growth_center_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'DataGrowthCenter'
      AND deleted_at = 0
    LIMIT 1
);

-- 仅在旧库尚未执行全量菜单重建时补建两个一级目录，保证后续菜单始终可在菜单管理中维护。
INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    icon, permission_code, visible, cacheable, sort_order, status, remark
)
SELECT
    0, 1, 'WorkbenchCenter', '工作台', '/workbench', 'BasicLayout',
    'lucide:panels-top-left', NULL, 1, 0, -850, 1, 'redirect=/workbench/tasks'
WHERE @workbench_center_id IS NULL;

SET @workbench_center_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'WorkbenchCenter'
      AND deleted_at = 0
    LIMIT 1
);

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    icon, permission_code, visible, cacheable, sort_order, status, remark
)
SELECT
    0, 1, 'DataGrowthCenter', '数据复盘', '/data-growth', 'BasicLayout',
    'lucide:chart-no-axes-combined', NULL, 1, 0, -650, 1,
    'redirect=/data-report'
WHERE @data_growth_center_id IS NULL;

SET @data_growth_center_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'DataGrowthCenter'
      AND deleted_at = 0
    LIMIT 1
);

UPDATE sys_menu
SET parent_id = 0,
    menu_type = 1,
    menu_name = '工作台',
    route_path = '/workbench',
    component = 'BasicLayout',
    icon = 'lucide:panels-top-left',
    permission_code = NULL,
    visible = 1,
    cacheable = 0,
    sort_order = -850,
    status = 1,
    remark = 'redirect=/workbench/tasks'
WHERE menu_code = 'WorkbenchCenter'
  AND deleted_at = 0;

UPDATE sys_menu
SET parent_id = 0,
    menu_type = 1,
    menu_name = '数据复盘',
    route_path = '/data-growth',
    component = 'BasicLayout',
    icon = 'lucide:chart-no-axes-combined',
    permission_code = NULL,
    visible = 1,
    cacheable = 0,
    sort_order = -650,
    status = 1,
    remark = 'redirect=/data-report'
WHERE menu_code = 'DataGrowthCenter'
  AND deleted_at = 0;

-- 日报中心是可见入口；其余三项为业务下钻和历史地址，不在侧栏显示。
UPDATE sys_menu
SET parent_id = @workbench_center_id,
    menu_type = 2,
    menu_name = '日报',
    route_path = '/workbench/daily-reports',
    component = '/workbench/daily-reports',
    icon = 'lucide:notebook-pen',
    permission_code = NULL,
    visible = 1,
    cacheable = 0,
    sort_order = 15,
    status = 1,
    remark = '日报填写、查询与导出入口；角色授权由菜单管理维护'
WHERE menu_code = 'WorkbenchDailyReports'
  AND deleted_at = 0
  AND @workbench_center_id IS NOT NULL;

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    icon, permission_code, visible, cacheable, sort_order, status, remark
)
SELECT
    @workbench_center_id, 2, 'WorkbenchDailyReports', '日报',
    '/workbench/daily-reports', '/workbench/daily-reports',
    'lucide:notebook-pen', NULL, 1, 0, 15, 1,
    '日报填写、查询与导出入口；角色授权由菜单管理维护'
WHERE @workbench_center_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'WorkbenchDailyReports'
        AND deleted_at = 0
  );

SET @daily_reports_menu_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'WorkbenchDailyReports'
      AND status = 1
      AND deleted_at = 0
    LIMIT 1
);

UPDATE sys_menu
SET parent_id = @daily_reports_menu_id,
    menu_type = 2,
    menu_name = '投放日报申请',
    route_path = '/workbench/delivery-daily-report',
    component = '/workbench/daily-report-application',
    icon = NULL,
    permission_code = NULL,
    visible = 0,
    cacheable = 0,
    sort_order = 10,
    status = 1,
    remark = '日报中心的投放日报填写页，不在侧栏显示'
WHERE menu_code = 'WorkbenchDailyReportApplication'
  AND deleted_at = 0
  AND @daily_reports_menu_id IS NOT NULL;

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    icon, permission_code, visible, cacheable, sort_order, status, remark
)
SELECT
    @daily_reports_menu_id, 2, 'WorkbenchDailyReportApplication', '投放日报申请',
    '/workbench/delivery-daily-report', '/workbench/daily-report-application',
    NULL, NULL, 0, 0, 10, 1, '日报中心的投放日报填写页，不在侧栏显示'
WHERE @daily_reports_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'WorkbenchDailyReportApplication'
        AND deleted_at = 0
  );

UPDATE sys_menu
SET parent_id = @daily_reports_menu_id,
    menu_type = 2,
    menu_name = '日报填写',
    route_path = '/workbench/daily-report-application',
    component = '/workbench/daily-report-application',
    icon = NULL,
    permission_code = NULL,
    visible = 0,
    cacheable = 0,
    sort_order = 20,
    status = 1,
    remark = '兼容历史日报填写链接，不在侧栏显示'
WHERE menu_code = 'LegacyWorkbenchDailyReportApplication'
  AND deleted_at = 0
  AND @daily_reports_menu_id IS NOT NULL;

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    icon, permission_code, visible, cacheable, sort_order, status, remark
)
SELECT
    @daily_reports_menu_id, 2, 'LegacyWorkbenchDailyReportApplication', '日报填写',
    '/workbench/daily-report-application', '/workbench/daily-report-application',
    NULL, NULL, 0, 0, 20, 1, '兼容历史日报填写链接，不在侧栏显示'
WHERE @daily_reports_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'LegacyWorkbenchDailyReportApplication'
        AND deleted_at = 0
  );

UPDATE sys_menu
SET parent_id = @daily_reports_menu_id,
    menu_type = 2,
    menu_name = '素材师月报',
    route_path = '/workbench/material-designer-monthly-report',
    component = '/workbench/material-designer-monthly-report',
    icon = NULL,
    permission_code = NULL,
    visible = 0,
    cacheable = 0,
    sort_order = 30,
    status = 1,
    remark = '日报中心的素材师月报填写页，不在侧栏显示'
WHERE menu_code = 'WorkbenchMaterialDesignerMonthlyReport'
  AND deleted_at = 0
  AND @daily_reports_menu_id IS NOT NULL;

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    icon, permission_code, visible, cacheable, sort_order, status, remark
)
SELECT
    @daily_reports_menu_id, 2, 'WorkbenchMaterialDesignerMonthlyReport', '素材师月报',
    '/workbench/material-designer-monthly-report',
    '/workbench/material-designer-monthly-report',
    NULL, NULL, 0, 0, 30, 1, '日报中心的素材师月报填写页，不在侧栏显示'
WHERE @daily_reports_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'WorkbenchMaterialDesignerMonthlyReport'
        AND deleted_at = 0
  );

UPDATE sys_menu
SET parent_id = @data_growth_center_id,
    menu_type = 2,
    menu_name = '项目运营面板',
    route_path = '/dashboard/project-daily-report',
    component = '/dashboard/project-daily-report',
    icon = 'lucide:calendar-range',
    permission_code = NULL,
    visible = 1,
    cacheable = 0,
    sort_order = 12,
    status = 1,
    remark = '按项目和代理线汇总每日运营数据的分析面板'
WHERE menu_code = 'ProjectDailyReport'
  AND deleted_at = 0
  AND @data_growth_center_id IS NOT NULL;

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    icon, permission_code, visible, cacheable, sort_order, status, remark
)
SELECT
    @data_growth_center_id, 2, 'ProjectDailyReport', '项目运营面板',
    '/dashboard/project-daily-report', '/dashboard/project-daily-report',
    'lucide:calendar-range', NULL, 1, 0, 12, 1,
    '按项目和代理线汇总每日运营数据的分析面板'
WHERE @data_growth_center_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'ProjectDailyReport'
        AND deleted_at = 0
  );

-- 新菜单默认仅授予管理员；其他角色通过菜单管理和角色权限按职责分配。
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, menu.id
FROM sys_role role
INNER JOIN sys_menu menu
    ON menu.menu_code IN (
        'WorkbenchDailyReports',
        'WorkbenchDailyReportApplication',
        'LegacyWorkbenchDailyReportApplication',
        'WorkbenchMaterialDesignerMonthlyReport',
        'ProjectDailyReport'
    )
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
