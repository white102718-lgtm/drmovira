-- 移除媒介资源中心的“出库与分配”页面；回收入口已合并到“资产管理”（MySQL 8+）。
START TRANSACTION;

SET @deleted_at = CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED);

SET @media_resource_assignments_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'MediaResourceAssignments'
      AND deleted_at = 0
    LIMIT 1
);

UPDATE sys_role_menu
SET deleted_at = @deleted_at
WHERE menu_id = @media_resource_assignments_id
  AND deleted_at = 0;

UPDATE sys_menu
SET status = 0,
    deleted_at = @deleted_at,
    updated_at = CURRENT_TIMESTAMP(3)
WHERE id = @media_resource_assignments_id
  AND deleted_at = 0;

COMMIT;

SELECT menu_code, menu_name, route_path, component, sort_order, status
FROM sys_menu
WHERE menu_code = 'MediaResourceAssignments';
