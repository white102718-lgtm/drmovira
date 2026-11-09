CREATE TABLE IF NOT EXISTS mig_channel_increment_batch (
    batch_key VARCHAR(100) NOT NULL COMMENT '服务端生成的不可变增量迁移批次键',
    environment VARCHAR(20) NOT NULL COMMENT '目标环境：TEST/PRODUCTION',
    state VARCHAR(20) NOT NULL DEFAULT 'applied' COMMENT '批次状态：applied/rolled_back',
    plan_hash CHAR(64) NOT NULL COMMENT '执行前重新计算并核对的SHA-256计划哈希',
    source_uuid CHAR(36) NOT NULL COMMENT '来源MySQL实例UUID',
    source_schema VARCHAR(64) NOT NULL COMMENT '来源数据库名',
    target_uuid CHAR(36) NOT NULL COMMENT '目标MySQL实例UUID',
    target_schema VARCHAR(64) NOT NULL COMMENT '目标数据库名',
    plan_json LONGTEXT NOT NULL COMMENT '不含凭据的渠道与费率预检摘要JSON',
    operator_id BIGINT UNSIGNED NOT NULL COMMENT '执行迁移的新系统用户ID',
    applied_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '目标库提交时间',
    PRIMARY KEY (batch_key),
    KEY idx_channel_increment_batch_environment (environment, state, applied_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='渠道增量迁移批次审计；批次提交后不可覆盖';

CREATE TABLE IF NOT EXISTS mig_channel_increment_mapping (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '映射记录主键',
    environment VARCHAR(20) NOT NULL COMMENT '目标环境：TEST/PRODUCTION',
    source_uuid CHAR(36) NOT NULL COMMENT '来源MySQL实例UUID',
    source_schema VARCHAR(64) NOT NULL COMMENT '来源数据库名',
    target_uuid CHAR(36) NOT NULL COMMENT '目标MySQL实例UUID',
    target_schema VARCHAR(64) NOT NULL COMMENT '目标数据库名',
    source_channel_id BIGINT UNSIGNED NOT NULL COMMENT '老系统渠道ID',
    target_channel_id BIGINT UNSIGNED NOT NULL COMMENT '当前环境新系统渠道ID',
    batch_key VARCHAR(100) NOT NULL COMMENT '逻辑关联增量批次，不建立数据库外键',
    operator_id BIGINT UNSIGNED NOT NULL COMMENT '执行迁移的新系统用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '映射创建时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0为有效；非0为软删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_channel_increment_source (
        environment, source_uuid, source_schema, target_uuid, target_schema, source_channel_id, deleted_at
    ),
    UNIQUE KEY uk_channel_increment_target (
        environment, target_uuid, target_schema, target_channel_id, deleted_at
    ),
    KEY idx_channel_increment_batch (batch_key),
    KEY idx_channel_increment_source_id (source_channel_id),
    KEY idx_channel_increment_target_id (target_channel_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='按环境和实例隔离的老渠道到新渠道增量映射';
