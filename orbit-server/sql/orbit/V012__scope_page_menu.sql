-- 仅新增已实现的范围冻结/成员查看页面，保留若依及ORBIT原菜单和动作归属。
-- 导航菜单不代替accounts.read动作授权；非内置管理员需显式获授31000/31011及31010。
INSERT IGNORE INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
VALUES(31011,'账户范围',31000,1,'account-scopes','orbit/accounts/scopes/index',1,1,'C','0','0','','list','admin',NOW(),'账户范围冻结及成员分页；操作仍要求当前accounts.read动作授权');
