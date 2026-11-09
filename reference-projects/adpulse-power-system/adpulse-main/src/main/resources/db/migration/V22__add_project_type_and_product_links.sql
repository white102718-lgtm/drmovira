ALTER TABLE pm_project
    ADD COLUMN project_type VARCHAR(30) NOT NULL DEFAULT 'game' COMMENT '项目类型' AFTER project_name,
    ADD INDEX idx_pm_project_type (project_type, deleted_at);

CREATE TABLE pm_project_product_link (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    project_id BIGINT UNSIGNED NOT NULL COMMENT '项目ID',
    product_url VARCHAR(1000) NOT NULL COMMENT '产品链接',
    sort_order INT UNSIGNED NOT NULL DEFAULT 0,
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_pm_project_product_link_deleted (project_id, product_url(255), deleted_at),
    KEY idx_pm_project_product_link_project (project_id, deleted_at, sort_order)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '项目产品链接';
