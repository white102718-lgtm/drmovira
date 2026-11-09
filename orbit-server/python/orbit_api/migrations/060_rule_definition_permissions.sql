-- 060：规则定义原六动作；页面未交付前父目录隐藏，不配置不存在的页面组件。
-- 所有原若依菜单保留；功能菜单与动作分开编译，不附送账户/监测/投放权限。
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark) VALUES
(31040,'规则管理',31000,4,'rules','ParentView',1,1,'M','1','0','rules.read','edit','admin',NOW(),'规则定义接口已注册；独立页面交付后再显示导航'),
(31041,'读取规则动作',31040,11,'#','',1,1,'F','0','0','rules.read','#','admin',NOW(),'只读当前可见规则及模拟上下文'),
(31042,'创建规则动作',31040,12,'#','',1,1,'F','0','0','rules.create','#','admin',NOW(),'创建草稿，不隐含启用资格'),
(31043,'编辑规则动作',31040,13,'#','',1,1,'F','0','0','rules.edit','#','admin',NOW(),'按版本编辑且复核完整账户范围'),
(31044,'启用规则动作',31040,14,'#','',1,1,'F','0','0','rules.enable','#','admin',NOW(),'要求真实有效模拟，不接模拟成功占位'),
(31045,'暂停规则动作',31040,15,'#','',1,1,'F','0','0','rules.pause','#','admin',NOW(),'暂停保留不可变历史'),
(31046,'归档规则动作',31040,16,'#','',1,1,'F','0','0','rules.archive','#','admin',NOW(),'归档保留历史，不硬删除');

INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,31040 FROM orbit_business_role br
 JOIN orbit_business_role_menu m ON m.tenant_id=br.tenant_id AND m.role_id=br.id
 WHERE m.menu_code='rules' AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm
 WHERE rm.role_id=br.native_role_id AND rm.menu_id=31040);
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,m.menu_id FROM orbit_business_role br
 JOIN orbit_business_role_action a ON a.tenant_id=br.tenant_id AND a.role_id=br.id
 JOIN sys_menu m ON m.perms=a.permission_code AND m.parent_id=31040
 WHERE NOT EXISTS(SELECT 1 FROM sys_role_menu rm
 WHERE rm.role_id=br.native_role_id AND rm.menu_id=m.menu_id);
