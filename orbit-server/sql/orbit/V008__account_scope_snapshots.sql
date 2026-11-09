-- 内部目录投影与范围冻结，不等同完整广告账户表或可信Meta导入器。
CREATE TABLE IF NOT EXISTS orbit_account_scope_directory (
    tenant_id CHAR(36) NOT NULL COMMENT '账户所属可信租户UUID',
    id CHAR(36) NOT NULL COMMENT '服务端账户UUID',
    external_id VARCHAR(64) NOT NULL COMMENT '外部账户数字ID字符串，不转浮点或long',
    name VARCHAR(10000) NOT NULL COMMENT '目录来源账户名，成员冻结时保留原值',
    operator_user_id CHAR(36) NULL COMMENT '当前投手业务UUID，NULL表示未分配',
    owner_team_id CHAR(36) NULL COMMENT '当前账户团队UUID，NULL不赋予普通用户数据权',
    vendor_id CHAR(36) NULL COMMENT '当前户商UUID，未绑定为NULL',
    currency CHAR(3) NOT NULL COMMENT '来源币种，不合并不同币种金额',
    account_status VARCHAR(16) NOT NULL COMMENT 'ACTIVE、DISABLED或UNKNOWN，来源状态不推测',
    auth_status VARCHAR(16) NOT NULL COMMENT 'AUTHORIZED、EXPIRED、REVOKED或UNKNOWN',
    source_state VARCHAR(24) NOT NULL DEFAULT 'UNVERIFIED' COMMENT '固定未验证；可信Meta导入器尚未接通，不可用于执行',
    revision BIGINT NOT NULL DEFAULT 1 COMMENT '目录账户版本，变更由后续发布器与目录时钟同事务推进',
    PRIMARY KEY (tenant_id,id),
    UNIQUE KEY uk_scope_directory_external (tenant_id,external_id),
    KEY idx_scope_directory_owner (tenant_id,operator_user_id,owner_team_id,id),
    FOREIGN KEY (tenant_id) REFERENCES orbit_tenant(id),
    CHECK (source_state='UNVERIFIED')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户范围选择所需内部投影，不含余额或凭据，不播种示例账户';
CREATE TABLE IF NOT EXISTS orbit_account_scope_clock (
    tenant_id CHAR(36) NOT NULL COMMENT '目录所属租户UUID',
    revision BIGINT NOT NULL DEFAULT 1 COMMENT '目录发布版本；不是完整跨模块权限scope_version',
    PRIMARY KEY (tenant_id),
    FOREIGN KEY (tenant_id) REFERENCES orbit_tenant(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='目录一致性门闩，真实发布器须持同一行锁更新成员与版本';
CREATE TABLE IF NOT EXISTS orbit_account_scope_snapshot (
    tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
    id CHAR(36) NOT NULL COMMENT '服务端生成范围快照UUID',
    actor_id BIGINT NOT NULL COMMENT '内部可信调用者若依用户ID',
    request_key CHAR(36) NOT NULL COMMENT '该用户范围生成幂等UUID',
    request_json LONGTEXT NOT NULL COMMENT '规范模式、IDs或过滤条件，不接受成员来源字段',
    request_hash CHAR(64) NOT NULL COMMENT '规范请求UTF8 SHA256',
    access_hash CHAR(64) NOT NULL COMMENT '生成时当前数据角色、主体和显式管理团队摘要',
    directory_revision BIGINT NOT NULL COMMENT '冻结目录发布版本，不冒充公开scope_version',
    members_hash CHAR(64) NULL COMMENT '排序成员ID、外部ID、名称及目录版本的SHA256',
    member_count INT NOT NULL DEFAULT 0 COMMENT '冻结去重成员数量，最多50000',
    ready TINYINT NOT NULL DEFAULT 0 COMMENT '1表示完整冻结提交，不表示可执行',
    created_at DATETIME(3) NOT NULL COMMENT '生成UTC时刻',
    PRIMARY KEY (tenant_id,id),
    UNIQUE KEY uk_scope_snapshot_request (tenant_id,actor_id,request_key),
    FOREIGN KEY (tenant_id) REFERENCES orbit_tenant(id),
    CHECK (JSON_VALID(request_json)),
    CHECK (member_count BETWEEN 0 AND 50000)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='内部账户选择快照，公开分页/权限版本和执行约束待补齐';
CREATE TABLE IF NOT EXISTS orbit_account_scope_member (
    tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
    snapshot_id CHAR(36) NOT NULL COMMENT '所属冻结快照UUID',
    account_id CHAR(36) NOT NULL COMMENT '冻结账户UUID',
    external_id VARCHAR(64) NOT NULL COMMENT '冻结外部数字ID字符串',
    name VARCHAR(10000) NOT NULL COMMENT '冻结目录账户名，不被后续重命名覆盖',
    directory_account_revision BIGINT NOT NULL COMMENT '冻结时该账户目录版本',
    PRIMARY KEY (tenant_id,snapshot_id,account_id),
    FOREIGN KEY (tenant_id,snapshot_id) REFERENCES orbit_account_scope_snapshot(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='不可变范围成员，当前权限与平台授权须在消费时重查';
