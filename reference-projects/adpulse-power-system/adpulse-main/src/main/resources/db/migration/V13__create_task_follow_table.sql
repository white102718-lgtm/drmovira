CREATE TABLE biz_task_follow (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '任务关注关系ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '逻辑关联biz_task.id',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '关注用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_task_follow_user_deleted (task_id, user_id, deleted_at),
    KEY idx_task_follow_user (user_id, deleted_at, task_id),
    KEY idx_task_follow_task (task_id, deleted_at, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户任务关注关系';
