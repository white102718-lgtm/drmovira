-- 主任务统一注册本轮业务入口；须在009、010业务迁移及页面接入完成后显式执行。
-- 不修改原若依菜单；页面菜单与动作分开，角色并集仍由服务端实时复核。
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark) VALUES
(31050,'素材库',31000,5,'assets','orbit/materials/index',1,1,'C','0','0','assets.read','upload','admin',NOW(),'ORBIT素材页面，读取动作仍需独立授权'),
(31070,'渠道管理',31000,7,'channels','orbit/channels/index',1,1,'C','0','0','channels.read','tree','admin',NOW(),'ORBIT渠道页面，数据范围由服务端校验'),
(31051,'读取素材动作',31050,11,'#','',1,1,'F','0','0','assets.read','#','admin',NOW(),'独立素材读取动作'),
(31052,'上传素材动作',31050,12,'#','',1,1,'F','0','0','assets.upload','#','admin',NOW(),'创建和完成有界上传会话'),
(31053,'编辑素材动作',31050,13,'#','',1,1,'F','0','0','assets.edit','#','admin',NOW(),'编辑素材及引用归属前复核范围'),
(31054,'删除素材动作',31050,14,'#','',1,1,'F','0','0','assets.delete','#','admin',NOW(),'逻辑归档不得绕过引用限制'),
(31055,'读取标签动作',31050,15,'#','',1,1,'F','0','0','tags.read','#','admin',NOW(),'素材标签分类只读权限'),
(31056,'新建标签动作',31050,16,'#','',1,1,'F','0','0','tags.create','#','admin',NOW(),'素材标签分类创建权限'),
(31057,'编辑标签动作',31050,17,'#','',1,1,'F','0','0','tags.edit','#','admin',NOW(),'素材标签分类编辑权限'),
(31058,'归档标签动作',31050,18,'#','',1,1,'F','0','0','tags.archive','#','admin',NOW(),'素材标签分类归档权限'),
(31071,'读取渠道动作',31070,11,'#','',1,1,'F','0','0','channels.read','#','admin',NOW(),'独立渠道读取动作'),
(31072,'新建渠道动作',31070,12,'#','',1,1,'F','0','0','channels.create','#','admin',NOW(),'渠道创建权限'),
(31073,'编辑渠道动作',31070,13,'#','',1,1,'F','0','0','channels.edit','#','admin',NOW(),'渠道编辑权限'),
(31074,'分配渠道动作',31070,14,'#','',1,1,'F','0','0','channels.assign','#','admin',NOW(),'渠道投手分配权限'),
(31075,'归档渠道动作',31070,15,'#','',1,1,'F','0','0','channels.archive','#','admin',NOW(),'渠道归档权限');

-- 复用原已登记的字典动作编号；31086仍属于放量门禁，不能挪用。
UPDATE sys_menu SET menu_name='业务字典',path='dictionaries',
 component='orbit/channels/ReferenceCatalog',menu_type='C',order_num=6,
 remark='引用目录受控导入与维护，保留system.dictionaries.manage独立动作'
 WHERE menu_id=31089 AND perms='system.dictionaries.manage' AND parent_id=31080;

-- 按已存在的业务角色显式授权编译原菜单关系；不因新增页面授予新动作。
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,m.menu_id
 FROM orbit_business_role br
 JOIN orbit_business_role_menu g ON g.tenant_id=br.tenant_id AND g.role_id=br.id
 JOIN sys_menu m ON (g.menu_code='assets' AND m.menu_id=31050)
                  OR (g.menu_code='channels' AND m.menu_id=31070)
 WHERE NOT EXISTS(SELECT 1 FROM sys_role_menu rm
   WHERE rm.role_id=br.native_role_id AND rm.menu_id=m.menu_id);
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,m.menu_id
 FROM orbit_business_role br
 JOIN orbit_business_role_action a ON a.tenant_id=br.tenant_id AND a.role_id=br.id
 JOIN sys_menu m ON m.perms=a.permission_code AND m.parent_id IN(31050,31070)
 WHERE NOT EXISTS(SELECT 1 FROM sys_role_menu rm
   WHERE rm.role_id=br.native_role_id AND rm.menu_id=m.menu_id);
