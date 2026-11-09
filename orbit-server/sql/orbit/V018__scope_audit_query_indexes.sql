-- 内部审计候选按目标租户与稳定时间/UUID排序；未知历史身份不回填。
SET @orbit_audit_page_index_exists = (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='orbit_account_scope_audit' AND index_name='idx_scope_audit_target_page');
SET @orbit_audit_page_index_sql = IF(@orbit_audit_page_index_exists=0, 'ALTER TABLE orbit_account_scope_audit ADD INDEX idx_scope_audit_target_page(target_tenant_id,created_at,id) COMMENT ''审计目标租户时间与UUID分页''', 'SELECT 1');
PREPARE orbit_audit_page_index_stmt FROM @orbit_audit_page_index_sql;
EXECUTE orbit_audit_page_index_stmt;
DEALLOCATE PREPARE orbit_audit_page_index_stmt;
SET @orbit_audit_subject_index_exists = (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='orbit_account_scope_audit' AND index_name='idx_scope_audit_subject');
SET @orbit_audit_subject_index_sql = IF(@orbit_audit_subject_index_exists=0, 'ALTER TABLE orbit_account_scope_audit ADD INDEX idx_scope_audit_subject(target_tenant_id,actor_subject_id,created_at,id) COMMENT ''审计历史操作者精确查询''', 'SELECT 1');
PREPARE orbit_audit_subject_index_stmt FROM @orbit_audit_subject_index_sql;
EXECUTE orbit_audit_subject_index_stmt;
DEALLOCATE PREPARE orbit_audit_subject_index_stmt;
