-- 062候选：仅在规则父页面实际接通且验证后由主线采用；不自动迁移现有预览。
-- 原若依菜单及060六动作全部保留，菜单入口不附送rules.read/create/edit动作。
UPDATE sys_menu SET visible='0',remark='ORBIT规则管理，原动作按会话独立授权'
 WHERE menu_id=31040 AND parent_id=31000 AND path='rules' AND menu_type='M';

INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark) VALUES
(31047,'规则列表与编辑',31040,1,'definitions','orbit/rules/index',1,1,'C','0','0','','list','admin',NOW(),
 '规则业务菜单入口；列表需rules.read，创建/编辑沿各自动作，不借读取或其它模块权限');

INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,31047 FROM orbit_business_role br
 JOIN orbit_business_role_menu m ON m.tenant_id=br.tenant_id AND m.role_id=br.id AND m.menu_code='rules'
 WHERE NOT EXISTS(SELECT 1 FROM sys_role_menu rm WHERE rm.role_id=br.native_role_id AND rm.menu_id=31047);
