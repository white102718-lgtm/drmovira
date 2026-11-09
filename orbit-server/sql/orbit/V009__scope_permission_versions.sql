-- 权限版本独立于账户目录版本；只维护当前已实现授权输入，未来资源授权表须纳入同一协议。
-- 无租户外键：保留已删除租户的版本墓碑，禁止复用同一UUID时回退版本。
CREATE TABLE IF NOT EXISTS orbit_scope_version (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID，删除后保留版本墓碑',
 version BIGINT NOT NULL DEFAULT 1 COMMENT '权限版本；授权事务原子递增，最大JavaScript安全整数',
 PRIMARY KEY (tenant_id),
 CHECK (version BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='当前租户权限变更时钟，溢出拒绝授权写入而非回绕';
INSERT IGNORE INTO orbit_scope_version(tenant_id) SELECT id FROM orbit_tenant;
CREATE TABLE IF NOT EXISTS orbit_account_scope_permission (
 tenant_id CHAR(36) NOT NULL COMMENT '冻结范围所属租户UUID',
 snapshot_id CHAR(36) NOT NULL COMMENT '冻结范围UUID',
 scope_version BIGINT NOT NULL COMMENT '冻结时权限版本；旧快照无记录时不能伪造默认版本',
 PRIMARY KEY(tenant_id,snapshot_id),
 FOREIGN KEY(tenant_id,snapshot_id) REFERENCES orbit_account_scope_snapshot(tenant_id,id),
 CHECK(scope_version BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='范围冻结权限版本，与头和成员同事务提交';

-- 单语句触发器，不依赖客户端DELIMITER；授权回滚时版本一起回滚。
CREATE TRIGGER IF NOT EXISTS orbit_sv_tenant_i AFTER INSERT ON orbit_tenant FOR EACH ROW
 INSERT INTO orbit_scope_version(tenant_id) VALUES(NEW.id) ON DUPLICATE KEY UPDATE version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_tenant_u AFTER UPDATE ON orbit_tenant FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id IN (OLD.id,NEW.id) AND (NOT (OLD.id <=> NEW.id) OR NOT (OLD.enabled <=> NEW.enabled));
CREATE TRIGGER IF NOT EXISTS orbit_sv_tenant_d AFTER DELETE ON orbit_tenant FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=OLD.id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_user_scope_i AFTER INSERT ON orbit_user_scope FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=NEW.tenant_id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_user_scope_u AFTER UPDATE ON orbit_user_scope FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id IN (OLD.tenant_id,NEW.tenant_id);
CREATE TRIGGER IF NOT EXISTS orbit_sv_user_scope_d AFTER DELETE ON orbit_user_scope FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=OLD.tenant_id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_biz_user_i AFTER INSERT ON orbit_business_user FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=NEW.tenant_id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_biz_user_u AFTER UPDATE ON orbit_business_user FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id IN (OLD.tenant_id,NEW.tenant_id);
CREATE TRIGGER IF NOT EXISTS orbit_sv_biz_user_d AFTER DELETE ON orbit_business_user FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=OLD.tenant_id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_biz_team_i AFTER INSERT ON orbit_business_team FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=NEW.tenant_id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_biz_team_u AFTER UPDATE ON orbit_business_team FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id IN (OLD.tenant_id,NEW.tenant_id);
CREATE TRIGGER IF NOT EXISTS orbit_sv_biz_team_d AFTER DELETE ON orbit_business_team FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=OLD.tenant_id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_manager_i AFTER INSERT ON orbit_business_team_manager FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=NEW.tenant_id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_manager_u AFTER UPDATE ON orbit_business_team_manager FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id IN (OLD.tenant_id,NEW.tenant_id);
CREATE TRIGGER IF NOT EXISTS orbit_sv_manager_d AFTER DELETE ON orbit_business_team_manager FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=OLD.tenant_id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_rule_i AFTER INSERT ON orbit_rule_draft FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=NEW.tenant_id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_rule_u AFTER UPDATE ON orbit_rule_draft FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id IN (OLD.tenant_id,NEW.tenant_id);
CREATE TRIGGER IF NOT EXISTS orbit_sv_rule_d AFTER DELETE ON orbit_rule_draft FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=OLD.tenant_id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_login_u AFTER UPDATE ON sys_user FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id IN (SELECT tenant_id FROM orbit_user_scope WHERE user_id IN (OLD.user_id,NEW.user_id)) AND (NOT (OLD.status <=> NEW.status) OR NOT (OLD.del_flag <=> NEW.del_flag) OR NOT (OLD.user_id <=> NEW.user_id));
CREATE TRIGGER IF NOT EXISTS orbit_sv_login_d AFTER DELETE ON sys_user FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id IN (SELECT tenant_id FROM orbit_user_scope WHERE user_id=OLD.user_id);
-- 若依角色和菜单可跨租户共用；这里保守使全部现存租户版本失效，不能只更新操作者租户。
CREATE TRIGGER IF NOT EXISTS orbit_sv_user_role_i AFTER INSERT ON sys_user_role FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_user_role_u AFTER UPDATE ON sys_user_role FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_user_role_d AFTER DELETE ON sys_user_role FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_role_menu_i AFTER INSERT ON sys_role_menu FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_role_menu_u AFTER UPDATE ON sys_role_menu FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_role_menu_d AFTER DELETE ON sys_role_menu FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_role_i AFTER INSERT ON sys_role FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_role_u AFTER UPDATE ON sys_role FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_role_d AFTER DELETE ON sys_role FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_menu_i AFTER INSERT ON sys_menu FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_menu_u AFTER UPDATE ON sys_menu FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
CREATE TRIGGER IF NOT EXISTS orbit_sv_menu_d AFTER DELETE ON sys_menu FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1;
-- 目录重命名和平台授权状态变化不改数据权限；新增、删除和归属变化需要递增。
CREATE TRIGGER IF NOT EXISTS orbit_sv_account_i AFTER INSERT ON orbit_account_scope_directory FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=NEW.tenant_id;
CREATE TRIGGER IF NOT EXISTS orbit_sv_account_u AFTER UPDATE ON orbit_account_scope_directory FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id IN (OLD.tenant_id,NEW.tenant_id) AND (NOT (OLD.tenant_id <=> NEW.tenant_id) OR NOT (OLD.operator_user_id <=> NEW.operator_user_id) OR NOT (OLD.owner_team_id <=> NEW.owner_team_id));
CREATE TRIGGER IF NOT EXISTS orbit_sv_account_d AFTER DELETE ON orbit_account_scope_directory FOR EACH ROW
 UPDATE orbit_scope_version SET version=version+1 WHERE tenant_id=OLD.tenant_id;
