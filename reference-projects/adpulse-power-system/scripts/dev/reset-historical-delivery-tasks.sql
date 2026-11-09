-- 历史投放任务重置，人工审核执行；不属于应用启动迁移。
-- 范围：biz_task 中全部有效 DELIVERY 任务，包含已完成、已撤回任务；不处理素材任务或草稿。
-- 保留基础信息、参考附件、关注关系、历史动态；软删除旧分配、交付、验收及交付附件绑定。
-- 执行前备份数据库并暂停任务写入。应配合新表单及强制表单校验的重新提交接口上线使用。
-- 在同一连接完整执行，遇到任何 SQL 错误立即 ROLLBACK，不要继续提交。
-- 默认演练并回滚；核对结果后，将末尾 ROLLBACK 改成 COMMIT，再完整执行。
-- 填写真实操作人 sys_user.id；未填写或用户无效时，目标集合为空，不修改任何任务。
SET @reset_operator_id = NULL;
SET @reset_reason = '投放流程升级：历史任务撤回，请创建者补齐投放明细和投手后重新提交';
SET @reset_now = UTC_TIMESTAMP(3);
SET @reset_deleted_at = CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED);

START TRANSACTION;

CREATE TEMPORARY TABLE tmp_delivery_reset_targets (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    previous_status VARCHAR(30) NOT NULL
);

INSERT INTO tmp_delivery_reset_targets (id, previous_status)
SELECT task.id, task.status
FROM biz_task task
WHERE task.task_type = 'DELIVERY'
  AND task.deleted_at = 0
  AND EXISTS (
      SELECT 1 FROM sys_user operator
      WHERE operator.id = @reset_operator_id AND operator.deleted_at = 0
  );

SELECT previous_status, COUNT(*) AS task_count
FROM tmp_delivery_reset_targets
GROUP BY previous_status;

-- 写入运维重置动态，保留原状态，避免冒充创建者的普通撤回操作。
INSERT INTO biz_task_activity (
    task_id, event_type, state, actor_id, actor_name, description, created_at, deleted_at
)
SELECT targets.id, 'ADMIN_RESET', 'WITHDRAWN', @reset_operator_id,
       '运维重置', CONCAT(@reset_reason, '；原状态：', targets.previous_status), @reset_now, 0
FROM tmp_delivery_reset_targets targets;

UPDATE biz_delivery_submission_object object_row
JOIN biz_delivery_task_submission submission ON submission.id = object_row.submission_id
JOIN tmp_delivery_reset_targets targets ON targets.id = submission.task_id
SET object_row.deleted_at = @reset_deleted_at
WHERE object_row.deleted_at = 0;

UPDATE biz_task_file_binding binding
JOIN tmp_delivery_reset_targets targets ON targets.id = binding.task_id
SET binding.deleted_at = @reset_deleted_at
WHERE binding.target_type = 'DELIVERY_SUBMISSION' AND binding.deleted_at = 0;

UPDATE biz_delivery_task_submission submission
JOIN tmp_delivery_reset_targets targets ON targets.id = submission.task_id
SET submission.deleted_at = @reset_deleted_at
WHERE submission.deleted_at = 0;

UPDATE biz_delivery_task_allocation allocation
JOIN tmp_delivery_reset_targets targets ON targets.id = allocation.task_id
SET allocation.deleted_at = @reset_deleted_at
WHERE allocation.deleted_at = 0;

UPDATE biz_task task
JOIN tmp_delivery_reset_targets targets ON targets.id = task.id
SET task.status = 'WITHDRAWN',
    task.owner_id = NULL,
    task.owner_name = NULL,
    task.assigner_id = NULL,
    task.assigner_name = NULL,
    task.assigned_at = NULL,
    task.accepted_at = NULL,
    task.completed_at = NULL,
    task.rejected_at = NULL,
    task.rejected_by = NULL,
    task.rejection_reason = NULL,
    task.withdrawn_at = @reset_now,
    task.withdraw_reason = @reset_reason,
    task.version = task.version + 1,
    task.updated_by = @reset_operator_id,
    task.updated_at = @reset_now;

SELECT task.status, COUNT(*) AS reset_task_count
FROM biz_task task
JOIN tmp_delivery_reset_targets targets ON targets.id = task.id
GROUP BY task.status;

-- 以下两项应均为 0。
SELECT COUNT(*) AS remaining_active_allocations
FROM biz_delivery_task_allocation allocation
JOIN tmp_delivery_reset_targets targets ON targets.id = allocation.task_id
WHERE allocation.deleted_at = 0;

SELECT COUNT(*) AS remaining_active_submissions
FROM biz_delivery_task_submission submission
JOIN tmp_delivery_reset_targets targets ON targets.id = submission.task_id
WHERE submission.deleted_at = 0;

ROLLBACK;
DROP TEMPORARY TABLE tmp_delivery_reset_targets;
