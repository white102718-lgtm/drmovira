-- 投放任务改为由项目指定负责人分配多个“团队—投手”执行项；素材任务不受影响。
ALTER TABLE biz_delivery_task_allocation
    DROP INDEX uk_delivery_task_team_deleted,
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ASSIGNED' COMMENT '执行状态：ASSIGNED/SUBMITTED/COMPLETED' AFTER sort_order,
    ADD COLUMN submitted_at DATETIME(3) NULL COMMENT '投手提交交付时间' AFTER status,
    ADD COLUMN completed_at DATETIME(3) NULL COMMENT '投放负责人验收通过时间' AFTER submitted_at,
    ADD UNIQUE KEY uk_delivery_task_team_operator_deleted (task_id, team_code, team_owner_id, deleted_at),
    ADD KEY idx_delivery_allocation_task_status (task_id, status, deleted_at),
    ADD CONSTRAINT ck_delivery_allocation_status CHECK (status IN ('ASSIGNED', 'SUBMITTED', 'COMPLETED'));

ALTER TABLE biz_delivery_task_submission
    ADD COLUMN allocation_id BIGINT UNSIGNED NULL COMMENT '对应团队—投手执行项ID' AFTER task_id,
    ADD KEY idx_delivery_submission_allocation (allocation_id, deleted_at);
