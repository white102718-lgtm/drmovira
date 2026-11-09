-- 新事件保存真实历史身份；既有事件未知，不以当前团队/UUID回填历史。
SET @orbit_audit_subject_exists = (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='orbit_account_scope_audit' AND column_name='actor_subject_id');
SET @orbit_audit_subject_sql = IF(@orbit_audit_subject_exists=0, 'ALTER TABLE orbit_account_scope_audit ADD actor_subject_id CHAR(36) NULL COMMENT ''生成时操作者业务UUID；旧事件未知，不以当前身份回填''', 'SELECT 1');
PREPARE orbit_audit_subject_stmt FROM @orbit_audit_subject_sql;
EXECUTE orbit_audit_subject_stmt;
DEALLOCATE PREPARE orbit_audit_subject_stmt;
SET @orbit_audit_team_exists = (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='orbit_account_scope_audit' AND column_name='actor_team_id');
SET @orbit_audit_team_sql = IF(@orbit_audit_team_exists=0, 'ALTER TABLE orbit_account_scope_audit ADD actor_team_id CHAR(36) NULL COMMENT ''生成时操作者所属团队UUID；历史冻结，不随调队改写''', 'SELECT 1');
PREPARE orbit_audit_team_stmt FROM @orbit_audit_team_sql;
EXECUTE orbit_audit_team_stmt;
DEALLOCATE PREPARE orbit_audit_team_stmt;
-- 只增加可分配审计读取动作，不增加占位页面，不改若依原菜单。
INSERT IGNORE INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time)
VALUES(31082,'ORBIT审计读取',31080,2,'#',1,0,'F','0','0','system.audit.read','#','admin',NOW());
