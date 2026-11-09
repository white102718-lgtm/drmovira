CREATE TABLE IF NOT EXISTS manual_task_execution (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '执行记录主键',
    task_code VARCHAR(100) NOT NULL COMMENT '任务编码',
    task_name VARCHAR(200) NOT NULL COMMENT '任务名称快照',
    status VARCHAR(20) NOT NULL COMMENT 'PENDING/RUNNING/SUCCESS/FAILED',
    triggered_by BIGINT NOT NULL COMMENT '触发人用户ID',
    triggered_by_name VARCHAR(100) NOT NULL COMMENT '触发人名称快照',
    triggered_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '触发时间',
    started_at DATETIME(3) NULL COMMENT '开始时间',
    finished_at DATETIME(3) NULL COMMENT '完成时间',
    heartbeat_at DATETIME(3) NULL COMMENT '心跳时间',
    log_content LONGTEXT NULL COMMENT '完整执行日志，包含错误日志',
    active_task_code VARCHAR(100) GENERATED ALWAYS AS (
        CASE WHEN deleted_at = 0 AND status IN ('PENDING', 'RUNNING') THEN task_code ELSE NULL END
    ) STORED,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_manual_task_active (active_task_code),
    KEY idx_manual_task_code_time (task_code, triggered_at),
    KEY idx_manual_task_status_time (status, triggered_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='手动任务触发事件';
