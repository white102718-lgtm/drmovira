-- 投放日报写入项目Google日报的按钮权限；数据库脚本需在发布前人工审核并执行。
SET @daily_reports_menu_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'WorkbenchDailyReports'
      AND deleted_at = 0
    LIMIT 1
);

UPDATE sys_menu
SET parent_id = @daily_reports_menu_id,
    menu_type = 3,
    menu_name = '推送项目日报',
    permission_code = 'workbench:daily:report:push',
    visible = 1,
    cacheable = 0,
    sort_order = 10,
    status = 1,
    remark = '允许配置项目日报模板、查看推送记录并将投放日报写入项目日报'
WHERE menu_code = 'WORKBENCH_DAILY_REPORT_PUSH'
  AND deleted_at = 0
  AND @daily_reports_menu_id IS NOT NULL;

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, permission_code,
    visible, cacheable, sort_order, status, remark
)
SELECT
    @daily_reports_menu_id, 3, 'WORKBENCH_DAILY_REPORT_PUSH', '推送项目日报',
    'workbench:daily:report:push', 1, 0, 10, 1,
    '允许配置项目日报模板、查看推送记录并将投放日报写入项目日报'
WHERE @daily_reports_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'WORKBENCH_DAILY_REPORT_PUSH'
        AND deleted_at = 0
  );

-- 新权限默认授予管理员；其他角色由菜单管理按需授权。
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, menu.id
FROM sys_role role
JOIN sys_menu menu
  ON menu.menu_code = 'WORKBENCH_DAILY_REPORT_PUSH'
 AND menu.deleted_at = 0
WHERE role.role_code = 'ADMIN'
  AND role.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1
      FROM sys_role_menu relation
      WHERE relation.role_id = role.id
        AND relation.menu_id = menu.id
        AND relation.deleted_at = 0
  );
