-- 首页改由 system 动态菜单下发；普通角色是否可见由 sys_role_menu 授权决定。
-- 本脚本不自动授予任何普通角色，超级管理员继续按现有查询规则拥有全部启用菜单。
START TRANSACTION;

UPDATE sys_menu
SET parent_id = 0,
    menu_type = 2,
    menu_name = '首页',
    route_path = '/home',
    component = '/home/index',
    icon = 'ion:home-outline',
    permission_code = NULL,
    visible = 1,
    cacheable = 1,
    external_link = NULL,
    sort_order = -999,
    status = 1,
    remark = 'AdPulse 首页；由角色菜单权限控制访问'
WHERE menu_code = 'Home'
  AND deleted_at = 0;

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    icon, permission_code, visible, cacheable, external_link, sort_order,
    status, remark
)
SELECT
    0, 2, 'Home', '首页', '/home', '/home/index',
    'ion:home-outline', NULL, 1, 1, NULL, -999,
    1, 'AdPulse 首页；由角色菜单权限控制访问'
WHERE NOT EXISTS (
    SELECT 1
    FROM sys_menu
    WHERE menu_code = 'Home'
      AND deleted_at = 0
);

COMMIT;
