CREATE TABLE biz_task_draft (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    draft_code VARCHAR(50) NOT NULL,
    task_type VARCHAR(20) NOT NULL,
    creator_id BIGINT UNSIGNED NOT NULL,
    creator_name VARCHAR(100) NOT NULL,
    title VARCHAR(200) NULL,
    project_id BIGINT UNSIGNED NULL,
    payload_json JSON NOT NULL,
    created_by BIGINT UNSIGNED NOT NULL,
    updated_by BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_task_draft_code_deleted (draft_code, deleted_at),
    KEY idx_task_draft_creator (creator_id, task_type, deleted_at, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务草稿';
