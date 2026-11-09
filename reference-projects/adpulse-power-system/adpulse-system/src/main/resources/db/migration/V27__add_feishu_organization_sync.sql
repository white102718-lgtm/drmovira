ALTER TABLE sys_department
    ADD COLUMN source_type VARCHAR(16) NOT NULL DEFAULT 'LOCAL' COMMENT '数据来源：LOCAL或FEISHU' AFTER remark,
    ADD COLUMN tenant_key VARCHAR(128) NULL COMMENT '飞书租户标识' AFTER source_type,
    ADD COLUMN external_id VARCHAR(128) NULL COMMENT '外部部门稳定标识' AFTER tenant_key,
    ADD COLUMN last_synced_at DATETIME(3) NULL COMMENT '最后同步时间' AFTER external_id,
    ADD UNIQUE KEY uk_department_source_external_deleted
        (source_type, tenant_key, external_id, deleted_at);

ALTER TABLE sys_user
    MODIFY COLUMN phone VARCHAR(32) NULL COMMENT '手机号；飞书用户在无权限时可为空',
    ADD COLUMN source_type VARCHAR(16) NOT NULL DEFAULT 'LOCAL' COMMENT '数据来源：LOCAL或FEISHU' AFTER remark,
    ADD COLUMN tenant_key VARCHAR(128) NULL COMMENT '飞书租户标识' AFTER source_type,
    ADD COLUMN external_id VARCHAR(128) NULL COMMENT '飞书用户稳定标识' AFTER tenant_key,
    ADD COLUMN feishu_open_id VARCHAR(128) NULL COMMENT '飞书应用维度用户标识' AFTER external_id,
    ADD COLUMN feishu_union_id VARCHAR(128) NULL COMMENT '飞书开放平台用户标识' AFTER feishu_open_id,
    ADD COLUMN last_synced_at DATETIME(3) NULL COMMENT '最后同步时间' AFTER feishu_union_id,
    ADD UNIQUE KEY uk_user_source_external_deleted
        (source_type, tenant_key, external_id, deleted_at);

CREATE TABLE sys_feishu_org_sync_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '同步日志ID',
    trigger_type VARCHAR(16) NOT NULL COMMENT '触发类型：PREVIEW或MANUAL',
    status VARCHAR(16) NOT NULL COMMENT '状态：RUNNING、SUCCESS或FAILED',
    department_total INT UNSIGNED NOT NULL DEFAULT 0,
    department_created INT UNSIGNED NOT NULL DEFAULT 0,
    department_updated INT UNSIGNED NOT NULL DEFAULT 0,
    department_disabled INT UNSIGNED NOT NULL DEFAULT 0,
    user_total INT UNSIGNED NOT NULL DEFAULT 0,
    user_created INT UNSIGNED NOT NULL DEFAULT 0,
    user_updated INT UNSIGNED NOT NULL DEFAULT 0,
    user_disabled INT UNSIGNED NOT NULL DEFAULT 0,
    conflict_count INT UNSIGNED NOT NULL DEFAULT 0,
    error_message VARCHAR(1000) NULL COMMENT '脱敏失败摘要',
    started_by BIGINT UNSIGNED NOT NULL COMMENT '发起人用户ID，逻辑关联sys_user.id',
    started_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    ended_at DATETIME(3) NULL,
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_feishu_org_log_started (started_at, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '飞书组织架构同步执行日志';
