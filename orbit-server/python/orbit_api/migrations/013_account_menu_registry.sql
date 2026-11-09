-- 主任务统一注册账户导航与独立动作；012业务表由账户线负责，原若依菜单保留。
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark) VALUES
(31010,'广告账户',31000,1,'accounts','orbit/accounts/index',1,1,'C','0','0','accounts.read','list','admin',NOW(),'账户目录与真实导入批次，未执行不能显示平台成功'),
(31011,'读取账户动作',31010,11,'#','',1,1,'F','0','0','accounts.read','#','admin',NOW(),'本人或明确授权团队范围读取'),
(31012,'导入账户动作',31010,12,'#','',1,1,'F','0','0','accounts.import','#','admin',NOW(),'原始标识预检、排队和逐行结果'),
(31013,'分配账户动作',31010,13,'#','',1,1,'F','0','0','accounts.assign','#','admin',NOW(),'当前归属调整独立授权，不改写历史事实'),
(31014,'同步账户动作',31010,14,'#','',1,1,'F','0','0','accounts.sync','#','admin',NOW(),'只读平台同步独立授权'),
(31015,'解绑账户动作',31010,15,'#','',1,1,'F','0','0','accounts.unbind','#','admin',NOW(),'解绑为业务状态迁移，不删除历史');

INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,31010 FROM orbit_business_role br
 JOIN orbit_business_role_menu g ON g.tenant_id=br.tenant_id AND g.role_id=br.id
 WHERE g.menu_code='accounts' AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm
   WHERE rm.role_id=br.native_role_id AND rm.menu_id=31010);
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,m.menu_id FROM orbit_business_role br
 JOIN orbit_business_role_action a ON a.tenant_id=br.tenant_id AND a.role_id=br.id
 JOIN sys_menu m ON m.perms=a.permission_code AND m.parent_id=31010
 WHERE NOT EXISTS(SELECT 1 FROM sys_role_menu rm
   WHERE rm.role_id=br.native_role_id AND rm.menu_id=m.menu_id);
