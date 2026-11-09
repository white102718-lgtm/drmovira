SET @system_management_id = (
    SELECT id FROM sys_menu
    WHERE menu_code IN ('SystemManagement', 'SYSTEM') AND deleted_at = 0
    ORDER BY CASE menu_code WHEN 'SystemManagement' THEN 0 ELSE 1 END LIMIT 1
);

INSERT INTO sys_menu (parent_id, menu_type, menu_code, menu_name, route_path, component, icon,
                      permission_code, visible, cacheable, sort_order, status, remark)
SELECT @system_management_id, 2, 'SYSTEM_MANUAL_TASK', '手动任务', '/system/manual-tasks',
       '/system/manual-tasks', 'lucide:play-circle', 'system:manual-task:list', 1, 0, 90, 1,
       '可重复人工触发的后台任务与执行日志'
WHERE @system_management_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE menu_code = 'SYSTEM_MANUAL_TASK' AND deleted_at = 0);

SET @manual_task_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'SYSTEM_MANUAL_TASK' AND deleted_at = 0 LIMIT 1
);

INSERT INTO sys_menu (parent_id, menu_type, menu_code, menu_name, permission_code, visible,
                      cacheable, sort_order, status, remark)
SELECT @manual_task_id, 3, 'SYSTEM_MANUAL_TASK_EXECUTE', '执行手动任务',
       'system:manual-task:execute', 1, 0, 10, 1, '允许触发手动任务'
WHERE @manual_task_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE menu_code = 'SYSTEM_MANUAL_TASK_EXECUTE' AND deleted_at = 0);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, menu.id
FROM sys_role role
JOIN sys_menu menu ON menu.menu_code IN ('SYSTEM_MANUAL_TASK', 'SYSTEM_MANUAL_TASK_EXECUTE')
                  AND menu.deleted_at = 0
WHERE role.role_code = 'ADMIN' AND role.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1 FROM sys_role_menu relation
      WHERE relation.role_id = role.id AND relation.menu_id = menu.id AND relation.deleted_at = 0
  );
