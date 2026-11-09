-- 业务角色UUID与原若依角色显式桥接；不将部门/角色名称当成数据范围，不复制原通配符。
CREATE TABLE orbit_business_role (
 tenant_id CHAR(36) NOT NULL COMMENT '角色所属可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '角色稳定业务UUID，API不暴露原数字ID',
 native_role_id BIGINT NOT NULL COMMENT '显式关联原若依sys_role.role_id；每个原角色仅属于一个业务租户',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '业务版本，修改采用If-Match',
 built_in TINYINT NOT NULL DEFAULT 0 COMMENT '1内置只读，允许复制为新业务角色；0可受控编辑',
 created_at DATETIME(3) NOT NULL COMMENT '角色映射创建UTC时刻，不代表旧原角色的历史创建时间',
 updated_at DATETIME(3) NOT NULL COMMENT '最近业务维护UTC时刻',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uk_business_role_native(native_role_id) COMMENT '防止一个原角色在不同租户重复映射',
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(native_role_id) REFERENCES sys_role(role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='ORBIT功能角色目录，数据角色与此表无关';
CREATE TABLE orbit_business_role_menu (
 tenant_id CHAR(36) NOT NULL COMMENT '角色所属租户UUID',
 role_id CHAR(36) NOT NULL COMMENT '业务角色UUID',
 menu_code VARCHAR(64) NOT NULL COMMENT '当前八业务菜单注册代码，按角色求并集',
 PRIMARY KEY(tenant_id,role_id,menu_code),
 FOREIGN KEY(tenant_id,role_id) REFERENCES orbit_business_role(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='功能角色菜单白名单，不根据动作推算菜单';
CREATE TABLE orbit_business_role_action (
 tenant_id CHAR(36) NOT NULL COMMENT '角色所属租户UUID',
 role_id CHAR(36) NOT NULL COMMENT '业务角色UUID',
 permission_code VARCHAR(100) NOT NULL COMMENT '注册动作白名单，不允许原若依通配符或退役动作',
 PRIMARY KEY(tenant_id,role_id,permission_code),
 FOREIGN KEY(tenant_id,role_id) REFERENCES orbit_business_role(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='功能角色动作白名单，与菜单独立并集后再求数据范围交集';
INSERT INTO orbit_business_role(tenant_id,id,native_role_id,built_in,created_at,updated_at)
SELECT tenant_id,'00000000-0000-0000-0000-000000000001',1,1,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3)
FROM orbit_user_scope WHERE user_id=1 AND tenant_id='00000000-0000-0000-0000-000000000001';
INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) SELECT tenant_id,id,'accounts' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) SELECT tenant_id,id,'launch' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) SELECT tenant_id,id,'monitor' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) SELECT tenant_id,id,'rules' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) SELECT tenant_id,id,'assets' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) SELECT tenant_id,id,'environments' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) SELECT tenant_id,id,'channels' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) SELECT tenant_id,id,'system' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'accounts.assign' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'accounts.import' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'accounts.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'accounts.sync' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'accounts.unbind' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'assets.delete' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'assets.edit' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'assets.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'assets.upload' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'channels.archive' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'channels.assign' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'channels.create' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'channels.edit' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'channels.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'environments.enroll' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'environments.probe' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'environments.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'environments.revoke' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'launch.create' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'launch.edit' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'launch.execute' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'launch.publish' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'launch.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'monitor.ad.delete' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'monitor.emergency_pause' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'monitor.manual.execute' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'monitor.optimization.execute' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'monitor.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'monitor.suggestion.edit' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'monitor.suggestion.ignore' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'reports.export' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'reports.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'rules.archive' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'rules.create' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'rules.edit' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'rules.enable' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'rules.pause' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'rules.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'system.audit.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'system.dictionaries.manage' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'system.integrations.manage' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'system.kill_switch' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'system.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'system.release.manage' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'system.roles.manage' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'system.teams.manage' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'system.users.manage' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'tags.archive' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'tags.create' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'tags.edit' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'tags.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'tasks.cancel' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'tasks.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'tasks.reconcile' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'tasks.retry' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'templates.archive' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'templates.create' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'templates.edit' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'templates.read' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) SELECT tenant_id,id,'templates.share' FROM orbit_business_role WHERE native_role_id=1;
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark)
VALUES(31084,'功能角色',31080,4,'roles','orbit/system/roles/index',1,1,'C','0','0',
 'system.roles.manage','peoples','admin',NOW(),'业务功能角色菜单与动作，与数据角色独立；原角色模块保留');
-- 下列仅为隐藏动作权限节点，不渲染尚未开发的业务页面；已有配置放量校验使用真实release动作。
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark) VALUES
(31082,'管理人员动作',31080,20,'#','',1,1,'F','0','0','system.users.manage','#','admin',NOW(),'独立动作授权，人员页面接通后显式升级为菜单'),
(31086,'管理放量门禁动作',31080,21,'#','',1,1,'F','0','0','system.release.manage','#','admin',NOW(),'用于配置RISK额外动作复核，不借配置权限隐含授予'),
(31087,'全局停止开关动作',31080,22,'#','',1,1,'F','0','0','system.kill_switch','#','admin',NOW(),'注册动作，非占位页面'),
(31088,'查看业务审计动作',31080,23,'#','',1,1,'F','0','0','system.audit.read','#','admin',NOW(),'注册动作，非占位页面'),
(31089,'管理业务字典动作',31080,24,'#','',1,1,'F','0','0','system.dictionaries.manage','#','admin',NOW(),'注册动作，非占位页面'),
(31090,'查看系统动作',31080,25,'#','',1,1,'F','0','0','system.read','#','admin',NOW(),'动作与system菜单独立保存，不以动作隐含授予菜单');
