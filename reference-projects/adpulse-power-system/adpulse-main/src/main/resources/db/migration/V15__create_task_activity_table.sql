CREATE TABLE biz_task_activity (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    state VARCHAR(40) NOT NULL,
    actor_id BIGINT UNSIGNED NOT NULL,
    actor_name VARCHAR(100) NOT NULL,
    description VARCHAR(1000) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_task_activity_task (task_id, deleted_at, created_at),
    KEY idx_task_activity_time (deleted_at, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务历史动态';
