-- 指标口径不可变版本目录；没有真实验证发布器时不允许声明已验证。
CREATE TABLE IF NOT EXISTS orbit_metric_profile_version (
    tenant_id CHAR(36) NOT NULL COMMENT '口径所属租户UUID',
    profile_id CHAR(36) NOT NULL COMMENT '可信服务端预分配的口径UUID',
    version VARCHAR(64) NOT NULL COMMENT '口径版本，同profile下不可覆盖，大小写敏感',
    source VARCHAR(16) NOT NULL COMMENT 'META真实连接器定义或FIXTURE测试定义，不代表已验证',
    body_json LONGTEXT NOT NULL COMMENT '完整口径定义规范JSON，事件未映射保持null',
    body_hash CHAR(64) NOT NULL COMMENT '规范定义UTF8 SHA256，防同版本改写',
    verification_state VARCHAR(24) NOT NULL DEFAULT 'UNVERIFIED' COMMENT '固定UNVERIFIED；真实证据发布器及对应迁移尚未完成',
    published TINYINT NOT NULL DEFAULT 0 COMMENT '定义发布标志：0事务预占、1定义和登记事件提交；不表示平台验证',
    created_at DATETIME(3) NOT NULL COMMENT '登记UTC时刻',
    PRIMARY KEY (tenant_id,profile_id,version),
    FOREIGN KEY (tenant_id) REFERENCES orbit_tenant(id),
    CHECK (JSON_VALID(body_json)),
    CHECK (source IN ('META','FIXTURE')),
    CHECK (verification_state='UNVERIFIED')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='指标归因口径定义目录，不把fixture或示例当已验证Meta';
CREATE TABLE IF NOT EXISTS orbit_metric_profile_event (
    id CHAR(36) NOT NULL COMMENT '口径登记事件UUID',
    tenant_id CHAR(36) NOT NULL COMMENT '所属租户UUID',
    profile_id CHAR(36) NOT NULL COMMENT '口径UUID',
    version VARCHAR(64) NOT NULL COMMENT '对应冻结口径版本',
    actor_id BIGINT NOT NULL COMMENT '当前内部可信调用方的若依操作用户ID',
    reason VARCHAR(500) NOT NULL COMMENT '口径登记人工原因，不保存凭据和平台原始响应',
    created_at DATETIME(3) NOT NULL COMMENT '登记事件UTC时刻，与版本同事务',
    PRIMARY KEY (id),
    UNIQUE KEY uk_metric_profile_event_version (tenant_id,profile_id,version),
    FOREIGN KEY (tenant_id,profile_id,version) REFERENCES orbit_metric_profile_version(tenant_id,profile_id,version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='口径版本登记审计，失败连同版本预占回滚';
