CREATE TABLE google_sync_data (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Google同步数据ID',
    mapping_id BIGINT UNSIGNED NOT NULL COMMENT '逻辑关联google_integration_mapping.id',
    start_date DATE NOT NULL COMMENT '数据日期',
    task_name VARCHAR(255) NOT NULL COMMENT '项目名称',
    subtask_name VARCHAR(255) NOT NULL COMMENT '任务线名称',
    spend_amount DECIMAL(20, 6) NULL COMMENT '花费金额',
    return_amount DECIMAL(20, 6) NULL COMMENT '回流金额',
    impressions BIGINT NULL COMMENT '展示次数',
    clicks BIGINT NULL COMMENT '点击量',
    registrations BIGINT NULL COMMENT '注册数',
    purchases BIGINT NULL COMMENT '购物次数',
    subscriptions BIGINT NULL COMMENT '订阅次数',
    media_placement VARCHAR(100) NULL COMMENT '媒体平台',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_google_sync_record
        (mapping_id, start_date, task_name, subtask_name, deleted_at),
    KEY idx_google_sync_mapping_date (mapping_id, start_date, deleted_at),
    KEY idx_google_sync_subtask_date (subtask_name, start_date, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = 'Google Sheets同步结果';
