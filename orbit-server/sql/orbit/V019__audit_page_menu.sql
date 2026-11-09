-- 审计列表与详情使用独立页面菜单；原审计动作及若依原菜单均保持。
INSERT IGNORE INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark)
VALUES(31083,'审计日志',31080,2,'audit','orbit/system/audit/index',1,1,'C','0','0','','documentation','admin',NOW(),'当前审计记录查询；页面和system.audit.read动作均须当前授权');
