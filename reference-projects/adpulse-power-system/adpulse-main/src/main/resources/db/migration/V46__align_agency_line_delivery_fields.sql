-- 代理线主数据补齐投放任务明细字段，并保存投放链接的不可变历史版本。
-- 本脚本由人工审核后执行，应用启动时不自动迁移。

ALTER TABLE pm_agency_line
    ADD COLUMN delivery_type VARCHAR(50) NULL COMMENT '投放明细类型' AFTER platform_value,
    MODIFY COLUMN delivery_url VARCHAR(2000) NULL COMMENT '当前投放链接',
    ADD COLUMN pixel_id VARCHAR(100) NULL COMMENT '像素ID' AFTER pixel_name,
    ADD COLUMN token_ciphertext TEXT NULL COMMENT 'Token的AES-GCM密文' AFTER pixel_id,
    ADD COLUMN test_code VARCHAR(200) NULL COMMENT '测试代码' AFTER token_ciphertext,
    ADD COLUMN cloak_url VARCHAR(2000) NULL COMMENT '斗篷链接' AFTER test_code;

CREATE TABLE pm_agency_line_delivery_url_history (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '投放链接历史ID',
    agency_line_id BIGINT UNSIGNED NOT NULL COMMENT '代理线ID，逻辑关联pm_agency_line.id',
    version_no INT UNSIGNED NOT NULL COMMENT '代理线内链接版本号',
    delivery_url VARCHAR(2000) NULL COMMENT '该版本投放链接，NULL表示清空',
    changed_by BIGINT UNSIGNED NULL COMMENT '修改人用户ID',
    changed_by_name VARCHAR(100) NULL COMMENT '修改人姓名快照',
    changed_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '版本产生时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0表示有效，其他值为软删除Unix毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_agency_line_url_version_deleted (agency_line_id, version_no, deleted_at),
    KEY idx_agency_line_url_history (agency_line_id, changed_at, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '代理线投放链接历史版本';

INSERT INTO pm_agency_line_delivery_url_history (
    agency_line_id,
    version_no,
    delivery_url,
    changed_by,
    changed_at
)
SELECT
    id,
    1,
    delivery_url,
    COALESCE(updated_by, created_by),
    updated_at
FROM pm_agency_line
WHERE deleted_at = 0
  AND delivery_url IS NOT NULL
  AND delivery_url != '';
