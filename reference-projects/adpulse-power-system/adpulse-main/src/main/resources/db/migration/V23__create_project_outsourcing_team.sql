CREATE TABLE pm_project_outsourcing_team (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    project_id BIGINT UNSIGNED NOT NULL COMMENT '项目ID',
    team_name VARCHAR(100) NOT NULL COMMENT '外包团队名称',
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_pm_project_outsourcing_team_deleted (project_id, team_name, deleted_at),
    KEY idx_pm_project_outsourcing_team_project (project_id, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '项目外包团队';
