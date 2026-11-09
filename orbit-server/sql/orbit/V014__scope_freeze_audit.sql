-- 只追加冻结成功事件；不补造升级前历史，不保存请求原文或幂等键。
CREATE TABLE IF NOT EXISTS orbit_account_scope_audit (
    id CHAR(36) NOT NULL COMMENT '服务端审计事件UUID',
    target_tenant_id CHAR(36) NOT NULL COMMENT '冻结资源实际所属目标租户UUID',
    snapshot_id CHAR(36) NOT NULL COMMENT '成功冻结快照UUID，保留历史引用不级联删除',
    actor_id BIGINT NOT NULL COMMENT '真实可信若依操作者ID，不伪造目标租户成员',
    home_tenant_id CHAR(36) NOT NULL COMMENT '操作时身份所属租户UUID',
    data_role VARCHAR(24) NOT NULL COMMENT '操作时已验证数据角色，不作为未来授权凭证',
    action VARCHAR(32) NOT NULL COMMENT '固定SCOPE_FROZEN成功事件，不记录重放为新成功',
    request_hash CHAR(64) NOT NULL COMMENT '规范请求SHA256摘要，不保存筛选或请求键原文',
    members_hash CHAR(64) NOT NULL COMMENT '不可变冻结成员摘要，不保存账户名或平台ID',
    member_count INT NOT NULL COMMENT '冻结去重成员数，含空范围0',
    home_version BIGINT NOT NULL COMMENT '操作时身份租户权限版本，独立保留',
    target_version BIGINT NOT NULL COMMENT '操作时目标租户权限版本，独立保留',
    created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '数据库生成的事件UTC时间，毫秒精度',
    PRIMARY KEY (id),
    UNIQUE KEY uk_scope_audit_success (target_tenant_id,snapshot_id,action),
    KEY idx_scope_audit_actor (home_tenant_id,actor_id,created_at,id),
    CHECK (member_count BETWEEN 0 AND 50000),
    CHECK (home_version BETWEEN 1 AND 9007199254740991),
    CHECK (target_version BETWEEN 1 AND 9007199254740991),
    CHECK (data_role IN ('USER','TEAM_ADMIN','SUPER_ADMIN')),
    CHECK (action='SCOPE_FROZEN')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='范围冻结成功审计，服务仅追加，与范围同事务提交，不补造旧记录';
