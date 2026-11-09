-- 按原HTTP合同保存完整ASCII幂等键；二进制比较区分大小写及空格，不截断或转换UUID。
ALTER TABLE orbit_account_scope_snapshot MODIFY request_key VARBINARY(128) NOT NULL COMMENT '当前actor的16至128字节可打印ASCII幂等键，逐字节比较';
-- 只增加可分配读取动作；账户页面路由另行实现，不建立占位页面。
INSERT IGNORE INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time)
VALUES(31010,'ORBIT账户读取',31000,3,'#',1,0,'F','0','0','accounts.read','#','admin',NOW());

