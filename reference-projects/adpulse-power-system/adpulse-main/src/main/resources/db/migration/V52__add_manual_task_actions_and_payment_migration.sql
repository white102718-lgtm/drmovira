ALTER TABLE manual_task_execution
    ADD COLUMN action_code VARCHAR(40) NOT NULL DEFAULT 'EXECUTE' COMMENT '本次触发的操作编码' AFTER task_name,
    ADD COLUMN action_name VARCHAR(100) NOT NULL DEFAULT '执行任务' COMMENT '本次触发的操作名称快照' AFTER action_code;

CREATE TABLE IF NOT EXISTS mig_legacy_payment_application (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '迁移账本主键',
    environment VARCHAR(20) NOT NULL COMMENT '目标环境：TEST/PRODUCTION',
    source_uuid VARCHAR(64) NOT NULL COMMENT '来源 MySQL 实例 UUID',
    source_schema VARCHAR(64) NOT NULL COMMENT '来源数据库名',
    target_uuid VARCHAR(64) NOT NULL COMMENT '目标 MySQL 实例 UUID',
    target_schema VARCHAR(64) NOT NULL COMMENT '目标数据库名',
    source_payment_id BIGINT UNSIGNED NOT NULL COMMENT '旧系统打款申请 ID',
    target_application_id BIGINT UNSIGNED NOT NULL COMMENT '新系统申请 ID',
    source_hash CHAR(64) NOT NULL COMMENT '来源记录 SHA-256 摘要',
    execution_id BIGINT UNSIGNED NOT NULL COMMENT '手动任务执行记录 ID',
    operator_id BIGINT UNSIGNED NOT NULL COMMENT '触发迁移的管理员 ID',
    migrated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '迁移时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除毫秒时间戳，0 表示有效',
    PRIMARY KEY (id),
    UNIQUE KEY uk_legacy_payment_source (
        environment, source_uuid, source_schema, target_uuid, target_schema,
        source_payment_id, deleted_at
    ),
    UNIQUE KEY uk_legacy_payment_target (target_application_id, deleted_at),
    KEY idx_legacy_payment_execution (execution_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='旧系统打款申请迁移账本';
