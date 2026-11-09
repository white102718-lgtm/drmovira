ALTER TABLE biz_delivery_task_submission
    ADD COLUMN actual_spend DECIMAL(18, 4) NOT NULL DEFAULT 0
        COMMENT '交付日期范围内Doris实际消耗，USD' AFTER actual_budget,
    ADD COLUMN daily_report_spend DECIMAL(18, 4) NOT NULL DEFAULT 0
        COMMENT '交付日期范围内本人日报花费，USD' AFTER actual_spend;
