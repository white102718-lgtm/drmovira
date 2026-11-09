ALTER TABLE pm_project_kpi
    DROP CHECK ck_pm_project_kpi_comparator,
    ADD COLUMN target_max_value DECIMAL(18, 4) NULL
        COMMENT '区间判断上限值；仅 comparator=between 时使用'
        AFTER target_value,
    MODIFY COLUMN comparator VARCHAR(10) NOT NULL
        COMMENT '比较方式：>、<、=、>=、<=、between',
    ADD CONSTRAINT ck_pm_project_kpi_comparator
        CHECK (comparator IN ('>', '<', '=', '>=', '<=', 'between')),
    ADD CONSTRAINT ck_pm_project_kpi_target_range
        CHECK (
            (comparator = 'between' AND target_max_value IS NOT NULL
                AND target_value < target_max_value)
            OR
            (comparator <> 'between' AND target_max_value IS NULL)
        );
