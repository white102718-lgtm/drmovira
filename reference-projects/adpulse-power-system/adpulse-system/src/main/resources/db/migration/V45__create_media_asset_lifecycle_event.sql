CREATE TABLE media_asset_lifecycle_event (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '资产生命周期事件主键',
    asset_id BIGINT UNSIGNED NOT NULL COMMENT '资产记录 ID，逻辑关联 media_asset.id',
    event_type VARCHAR(32) NOT NULL COMMENT '事件类型：STOCKED/UPDATED/ASSIGNED/RELEASED/RETURN_REQUESTED/RETURN_COMPLETED/DISABLED/DELETED',
    status VARCHAR(24) NULL COMMENT '事件发生后的库存状态快照',
    application_id BIGINT UNSIGNED NULL COMMENT '关联申请单 ID，逻辑关联 media_asset_application.id',
    actor_id BIGINT UNSIGNED NULL COMMENT '执行操作的用户 ID',
    actor_name VARCHAR(100) NULL COMMENT '执行操作的用户名称快照',
    usage_user_id BIGINT UNSIGNED NULL COMMENT '使用人用户 ID 快照',
    usage_user_name VARCHAR(100) NULL COMMENT '使用人名称快照',
    project_name VARCHAR(255) NULL COMMENT '项目或渠道名称快照',
    team_name VARCHAR(255) NULL COMMENT '使用团队名称快照',
    description VARCHAR(500) NULL COMMENT '不含敏感信息的事件说明',
    occurred_at DATETIME(3) NOT NULL COMMENT '事件发生时间（UTC）',
    PRIMARY KEY (id),
    KEY idx_media_asset_lifecycle_asset_time (asset_id, occurred_at, id),
    KEY idx_media_asset_lifecycle_application (application_id, occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='普通库存资产生命周期事件账本；用于只读追溯，不保存密码、令牌或原始密文';
