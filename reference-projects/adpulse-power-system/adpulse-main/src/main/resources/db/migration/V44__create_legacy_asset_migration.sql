-- 人工在所选新测试/新生产 adpulse_system 分别执行；不修改资产表，不自动执行。
-- 执行前核对 SELECT @@server_uuid, DATABASE();
-- 新测试 172.31.23.105：16903961-99f2-11f1-a1fe-86f52840e8b4 / adpulse_system。
-- 新生产 172.31.8.119：17c4f6b3-a2cc-11f1-99a8-ea697aa9ac3a / adpulse_system。
-- 已部署旧版三张表的环境无需重复建表；本次双环境改造不增加表字段。
CREATE TABLE mig_asset_mutex (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY
) ENGINE=InnoDB;
INSERT INTO mig_asset_mutex (id) VALUES (1);

CREATE TABLE mig_asset_job (
    row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    id CHAR(36) NOT NULL,
    state VARCHAR(20) NOT NULL,
    plan_hash CHAR(64) NULL,
    source_hash CHAR(64) NULL,
    channel_hash CHAR(64) NULL,
    operator_id BIGINT UNSIGNED NOT NULL,
    source_count INT NOT NULL DEFAULT 0,
    total INT NOT NULL DEFAULT 0,
    completed INT NOT NULL DEFAULT 0,
    isolated INT NOT NULL DEFAULT 0,
    duplicates INT NOT NULL DEFAULT 0,
    error VARCHAR(255) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_mig_asset_job_id (id),
    KEY idx_mig_asset_job_work (state, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 迁移任务/明细为审计记录，不是业务表，不软删。
CREATE TABLE mig_asset_item (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    job_id CHAR(36) NOT NULL,
    account_id TEXT NOT NULL,
    target_id BIGINT UNSIGNED NULL,
    action VARCHAR(20) NOT NULL,
    state VARCHAR(20) NOT NULL,
    reason VARCHAR(255) NULL,
    source_json LONGTEXT NOT NULL,
    before_json LONGTEXT NULL,
    desired_json LONGTEXT NULL,
    after_json LONGTEXT NULL,
    KEY idx_mig_asset_item_job (job_id, state, id),
    KEY idx_mig_asset_item_page (job_id, id),
    KEY idx_mig_asset_item_target (target_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
