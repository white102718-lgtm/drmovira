-- 仅支持在当前服务端允许租户内按actor+UUID定位；不是授权表，不改变原菜单或成员。
SET @orbit_scope_locator_exists = (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='orbit_account_scope_snapshot' AND index_name='idx_scope_actor_locator');
SET @orbit_scope_locator_sql = IF(@orbit_scope_locator_exists=0, 'ALTER TABLE orbit_account_scope_snapshot ADD INDEX idx_scope_actor_locator (actor_id,id,tenant_id)', 'SELECT 1');
PREPARE orbit_scope_locator_statement FROM @orbit_scope_locator_sql;
EXECUTE orbit_scope_locator_statement;
DEALLOCATE PREPARE orbit_scope_locator_statement;
