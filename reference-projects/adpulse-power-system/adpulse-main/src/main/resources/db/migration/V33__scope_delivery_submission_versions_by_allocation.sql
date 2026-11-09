-- 投放交付版本按“团队—投手”执行项独立编号；同一任务中的不同投手均可从 v1 开始。
ALTER TABLE biz_delivery_task_submission
    DROP INDEX uk_delivery_submission_version_deleted,
    ADD UNIQUE KEY uk_delivery_submission_allocation_version_deleted (allocation_id, version_no, deleted_at);

-- 修复在旧的“任务级版本号”规则下已创建的交付记录。
UPDATE biz_delivery_task_submission submission
JOIN (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY allocation_id
               ORDER BY submitted_at, id
           ) AS allocation_version_no
    FROM biz_delivery_task_submission
    WHERE allocation_id IS NOT NULL
      AND deleted_at = 0
) ranked ON ranked.id = submission.id
SET submission.version_no = ranked.allocation_version_no;
