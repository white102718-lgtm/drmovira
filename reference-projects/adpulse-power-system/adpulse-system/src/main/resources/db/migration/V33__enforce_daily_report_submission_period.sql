-- 报表提交周期由服务端按规则时区计算；同一规则、提交人和周期只能保留一条可编辑记录。
ALTER TABLE sys_daily_report_submission
    ADD COLUMN period_key DATE NULL COMMENT '规则周期的稳定起点；用于日报唯一性校验' AFTER report_date;

-- 旧记录缺少周期快照，先按原业务日期保留，避免迁移过程丢失历史日报。
UPDATE sys_daily_report_submission
SET period_key = report_date
WHERE period_key IS NULL;

-- 早期允许同一用户在同一天重复提交日报。保留每组最新记录的原周期，
-- 将较早记录映射至与主业务日期隔离的归档键，确保历史记录不会阻塞新约束。
UPDATE sys_daily_report_submission submission
JOIN (
    SELECT id
    FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY rule_id, submitted_by_id, period_key
                   ORDER BY id DESC
               ) AS row_number_in_period
        FROM sys_daily_report_submission
    ) ranked_submissions
    WHERE row_number_in_period > 1
) duplicate_submissions ON duplicate_submissions.id = submission.id
SET submission.period_key = DATE_SUB(DATE '9000-01-01', INTERVAL submission.id DAY);

ALTER TABLE sys_daily_report_submission
    MODIFY COLUMN period_key DATE NOT NULL COMMENT '规则周期的稳定起点；用于日报唯一性校验',
    ADD UNIQUE KEY uk_daily_report_submission_period (rule_id, submitted_by_id, period_key);
