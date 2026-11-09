-- 团队业务菜单仅新增到ORBIT系统下，原若依菜单完整保留；配套真实Python接口及前端页面。
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark)
VALUES(31083,'团队管理',31080,3,'teams','orbit/system/teams/index',1,1,'C','0','0',
 'system.teams.manage','tree','admin',NOW(),'ORBIT业务团队目录；原若依部门不自动授予业务范围');
ALTER TABLE orbit_business_team ADD KEY idx_business_team_created(tenant_id,created_at,id)
 COMMENT '租户内UTC创建日期过滤；旧记录创建时间未知为NULL';
