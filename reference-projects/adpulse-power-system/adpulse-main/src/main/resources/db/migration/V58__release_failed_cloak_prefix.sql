-- 部署前人工执行：明确失败的斗篷记录保留审计，但不再占用推广链接前缀。
ALTER TABLE biz_cloak
    DROP INDEX uk_cloak_prefix_domain_deleted,
    ADD COLUMN prefix_occupancy TINYINT
        GENERATED ALWAYS AS (
            CASE
                WHEN deleted_at = 0 AND status IN (0, 1, 3) THEN 1
                ELSE NULL
            END
        ) STORED
        COMMENT '待确认、成功或待核对记录占用推广链接前缀；明确失败为空',
    ADD UNIQUE KEY uk_cloak_prefix_domain_active (
        ad_url,
        gen_id,
        prefix_occupancy,
        deleted_at
    ) COMMENT '未明确失败的有效记录不可重复占用服务商推广链接前缀';
