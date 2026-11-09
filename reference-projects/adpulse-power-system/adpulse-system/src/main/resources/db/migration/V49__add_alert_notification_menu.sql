-- 将原弹窗能力升级为媒介资源中心下的独立预警通知页面。
SET @media_resource_id = (
    SELECT id FROM sys_menu
    WHERE route_path = '/media-resources' AND deleted_at = 0
    ORDER BY id LIMIT 1
);

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component, icon,
    permission_code, visible, cacheable, sort_order, status, remark
)
SELECT
    @media_resource_id, 2, 'MediaResourceAlertNotifications', '预警通知',
    '/media-resources/alert-notifications', '/media-resources/alert-notifications/index',
    'lucide:bell-ring', 'media-resource:alert-notification:manage', 1, 0, 90, 1,
    '广告户封号、限额变化和消耗上限预警配置及提醒记录'
WHERE @media_resource_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sys_menu
      WHERE menu_code = 'MediaResourceAlertNotifications' AND deleted_at = 0
  );

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, menu.id
FROM sys_role role
INNER JOIN sys_menu menu
    ON menu.menu_code = 'MediaResourceAlertNotifications'
   AND menu.status = 1 AND menu.deleted_at = 0
WHERE role.role_code = 'ADMIN'
  AND role.status = 1 AND role.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1 FROM sys_role_menu relation
      WHERE relation.role_id = role.id AND relation.menu_id = menu.id AND relation.deleted_at = 0
  );
