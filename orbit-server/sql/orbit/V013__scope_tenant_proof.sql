-- 仅内部会话范围冻结使用；旧快照不补写新版本，缺少绑定时拒绝复用。
CREATE TABLE IF NOT EXISTS orbit_account_scope_tenant_proof (
    tenant_id CHAR(36) NOT NULL COMMENT '快照实际所属目标租户UUID',
    snapshot_id CHAR(36) NOT NULL COMMENT '不可变冻结快照UUID',
    actor_id BIGINT NOT NULL COMMENT '生成时真实若依操作者ID，不伪造目标租户成员',
    home_tenant_id CHAR(36) NOT NULL COMMENT '操作者生成时所属可信租户UUID',
    data_role VARCHAR(24) NOT NULL COMMENT '生成时当前数据角色，读取时重新校验',
    home_version BIGINT NOT NULL COMMENT '生成时身份租户权限版本，独立比较不相加',
    target_version BIGINT NOT NULL COMMENT '生成时目标租户权限版本，独立比较不相加',
    PRIMARY KEY (tenant_id,snapshot_id),
    FOREIGN KEY (tenant_id,snapshot_id) REFERENCES orbit_account_scope_snapshot(tenant_id,id),
    FOREIGN KEY (home_tenant_id) REFERENCES orbit_tenant(id),
    CHECK (home_version BETWEEN 1 AND 9007199254740991),
    CHECK (target_version BETWEEN 1 AND 9007199254740991),
    CHECK (data_role IN ('USER','TEAM_ADMIN','SUPER_ADMIN'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='范围冻结双租户版本绑定，不是公开scope_version或审计替代';
