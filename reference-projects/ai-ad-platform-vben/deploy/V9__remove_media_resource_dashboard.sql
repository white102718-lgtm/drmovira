-- 移除媒介资源中心的“资源看板”，并将目录默认入口切换到“资产管理”（MySQL 8+）。
START TRANSACTION;

SET @deleted_at = CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED);

SET @media_resource_dashboard_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'MediaResourceDashboard'
      AND deleted_at = 0
    LIMIT 1
);

UPDATE sys_role_menu
SET deleted_at = @deleted_at
WHERE menu_id = @media_resource_dashboard_id
  AND deleted_at = 0;

UPDATE sys_menu
SET status = 0,
    deleted_at = @deleted_at,
    updated_at = CURRENT_TIMESTAMP(3)
WHERE id = @media_resource_dashboard_id
  AND deleted_at = 0;

UPDATE sys_menu
SET remark = 'redirect=/media-resources/accounts',
    updated_at = CURRENT_TIMESTAMP(3)
WHERE menu_code = 'MediaResourceCenter'
  AND deleted_at = 0;

UPDATE sys_menu
SET sort_order = 10,
    updated_at = CURRENT_TIMESTAMP(3)
WHERE menu_code = 'MediaResourceAccounts'
  AND deleted_at = 0;

COMMIT;

SELECT menu_code, menu_name, route_path, component, sort_order, status
FROM sys_menu
WHERE menu_code IN ('MediaResourceCenter', 'MediaResourceAccounts')
  AND deleted_at = 0
ORDER BY menu_type, sort_order;
