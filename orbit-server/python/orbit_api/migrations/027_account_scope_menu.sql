-- 范围冻结隐藏二级页保留原路径；31011仍是读取账户F动作，禁止覆盖。
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark) VALUES
(31016,'账户范围',31000,16,'account-scopes','orbit/accounts/scopes/index',1,1,
 'C','1','0','accounts.read','list','admin',NOW(),'账户页面内入口；隐藏二级页，授权仍按accounts菜单和原读取动作');
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,31016 FROM orbit_business_role br
 JOIN orbit_business_role_action a ON a.tenant_id=br.tenant_id AND a.role_id=br.id
 WHERE a.permission_code='accounts.read' AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm
  WHERE rm.role_id=br.native_role_id AND rm.menu_id=31016);
