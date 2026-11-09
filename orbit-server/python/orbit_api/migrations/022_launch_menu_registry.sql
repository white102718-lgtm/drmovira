-- 主线统一注册投放入口和模板二级页动作；显式升级，不更改原若依菜单。
-- 菜单权限和各动作独立，templates.read不隐含launch.read或执行/发布权限。
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark) VALUES
(31020,'投放管理',31000,2,'launch','orbit/launch/index',1,1,'C','0','0','launch.read','build','admin',NOW(),'投放及模板二级页，服务端逐次复核动作与数据范围'),
(31021,'读取计划动作',31020,11,'#','',1,1,'F','0','0','launch.read','#','admin',NOW(),'读取可见投放计划'),
(31022,'创建计划动作',31020,12,'#','',1,1,'F','0','0','launch.create','#','admin',NOW(),'创建草稿及模板应用，不表示已执行'),
(31023,'编辑计划动作',31020,13,'#','',1,1,'F','0','0','launch.edit','#','admin',NOW(),'版本化编辑及分配，来源另验读取权限'),
(31024,'执行计划动作',31020,14,'#','',1,1,'F','0','0','launch.execute','#','admin',NOW(),'执行动作独立授权，须通过实时安全预检'),
(31025,'发布计划动作',31020,15,'#','',1,1,'F','0','0','launch.publish','#','admin',NOW(),'独立发布及更严格风控门禁'),
(310201,'读取模板动作',31020,21,'#','',1,1,'F','0','0','templates.read','#','admin',NOW(),'读取本人及冻结分享接收范围模板'),
(310202,'创建模板动作',31020,22,'#','',1,1,'F','0','0','templates.create','#','admin',NOW(),'创建独立无账户身份与素材分配的配置模板'),
(310203,'编辑模板动作',31020,23,'#','',1,1,'F','0','0','templates.edit','#','admin',NOW(),'模板版本化编辑'),
(310204,'分享模板动作',31020,24,'#','',1,1,'F','0','0','templates.share','#','admin',NOW(),'显式冻结分享接收者，不扩展数据角色'),
(310205,'归档模板动作',31020,25,'#','',1,1,'F','0','0','templates.archive','#','admin',NOW(),'归档模板保留历史');

-- 仅编译既有业务授权，不因新增导航授予任何业务动作。
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,31020 FROM orbit_business_role br
 JOIN orbit_business_role_menu g ON g.tenant_id=br.tenant_id AND g.role_id=br.id
 WHERE g.menu_code='launch' AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm
   WHERE rm.role_id=br.native_role_id AND rm.menu_id=31020);
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,m.menu_id FROM orbit_business_role br
 JOIN orbit_business_role_action a ON a.tenant_id=br.tenant_id AND a.role_id=br.id
 JOIN sys_menu m ON m.perms=a.permission_code AND m.parent_id=31020
 WHERE NOT EXISTS(SELECT 1 FROM sys_role_menu rm
   WHERE rm.role_id=br.native_role_id AND rm.menu_id=m.menu_id);
