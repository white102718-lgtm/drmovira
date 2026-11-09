-- HTTP请求关联与幂等键分离；旧事件及非HTTP调用保持未知，不回填伪造值。
SET @orbit_audit_request_exists = (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='orbit_account_scope_audit' AND column_name='request_id');
SET @orbit_audit_request_sql = IF(@orbit_audit_request_exists=0, 'ALTER TABLE orbit_account_scope_audit ADD request_id CHAR(36) NULL COMMENT ''首次成功冻结的服务端HTTP请求UUID；旧事件与非HTTP调用未知''', 'SELECT 1');
PREPARE orbit_audit_request_stmt FROM @orbit_audit_request_sql;
EXECUTE orbit_audit_request_stmt;
DEALLOCATE PREPARE orbit_audit_request_stmt;
