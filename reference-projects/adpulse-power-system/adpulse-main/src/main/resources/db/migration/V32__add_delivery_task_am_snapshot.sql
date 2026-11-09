ALTER TABLE biz_delivery_task
    ADD COLUMN am_user_id BIGINT UNSIGNED NULL COMMENT '创建时项目 AM 用户ID快照' AFTER planned_start_at,
    ADD COLUMN am_user_name VARCHAR(100) NULL COMMENT '创建时项目 AM 姓名快照' AFTER am_user_id,
    ADD KEY idx_delivery_task_am_user (am_user_id, deleted_at);

-- 历史投放任务未保存 AM 快照，以当前关联项目的 AM 补齐；不会覆盖新任务已有快照。
UPDATE biz_delivery_task delivery
INNER JOIN biz_task task
    ON task.id = delivery.task_id
    AND task.task_type = 'DELIVERY'
    AND task.deleted_at = 0
INNER JOIN pm_project project
    ON project.id = task.project_id
    AND project.deleted_at = 0
SET delivery.am_user_id = project.am_user_id,
    delivery.am_user_name = project.am_name
WHERE delivery.deleted_at = 0
  AND delivery.am_user_id IS NULL
  AND delivery.am_user_name IS NULL;
