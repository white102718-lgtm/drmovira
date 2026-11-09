-- 主线042候选：指标目录只读页面；待041/query/前端接线后才复制为实际迁移。
-- 沿用原monitor菜单动作；不新增metric_profiles.read，不修改若依原监控菜单。
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark) VALUES
(31030,'广告投放数据',31000,3,'monitor','ParentView',1,0,'M','0','0','monitor.read','chart','admin',NOW(),'ORBIT原广告数据菜单，当前先交付指标配置目录，其他数据流程仍待实现'),
(31031,'读取广告数据动作',31030,11,'#','',1,1,'F','0','0','monitor.read','#','admin',NOW(),'原monitor.read实时读取动作，不隐含执行或发行权限'),
(310301,'指标配置',31030,1,'metric-profiles','orbit/monitor/MetricProfiles',1,1,'C','0','0','monitor.read','list','admin',NOW(),'原MetricProfile只读目录，配置发行仍要求原system.release.manage');

-- 只编译已有业务角色明确授予的菜单与动作，不默认提升任何用户权限。
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,31030 FROM orbit_business_role br
 JOIN orbit_business_role_menu g ON g.tenant_id=br.tenant_id AND g.role_id=br.id
 WHERE g.menu_code='monitor' AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm
  WHERE rm.role_id=br.native_role_id AND rm.menu_id=31030);
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,m.menu_id FROM orbit_business_role br
 JOIN orbit_business_role_action a ON a.tenant_id=br.tenant_id AND a.role_id=br.id
 JOIN sys_menu m ON m.menu_id IN(31031,310301) AND m.perms=a.permission_code
 WHERE a.permission_code='monitor.read' AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm
  WHERE rm.role_id=br.native_role_id AND rm.menu_id=m.menu_id);
