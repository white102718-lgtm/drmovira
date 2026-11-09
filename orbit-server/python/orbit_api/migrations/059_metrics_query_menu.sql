-- 059：接入新增投放数据查询页，保留原monitor父菜单、指标配置及若依原菜单。
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark) VALUES
(310302,'投放数据查询',31030,0,'data','orbit/monitor/index',1,1,'C','0','0','monitor.read','chart','admin',NOW(),'原Metrics查询及详情；来源未就绪明确错误，不隐含配置发行或广告执行');

-- 只编译原角色明确具有的monitor菜单与read动作，不授予额外数据范围。
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,310302 FROM orbit_business_role br
 JOIN orbit_business_role_menu m ON m.tenant_id=br.tenant_id AND m.role_id=br.id AND m.menu_code='monitor'
 JOIN orbit_business_role_action a ON a.tenant_id=br.tenant_id AND a.role_id=br.id AND a.permission_code='monitor.read'
 WHERE NOT EXISTS(SELECT 1 FROM sys_role_menu rm WHERE rm.role_id=br.native_role_id AND rm.menu_id=310302);
