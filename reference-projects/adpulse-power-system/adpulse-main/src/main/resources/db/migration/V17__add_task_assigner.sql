ALTER TABLE biz_task
    ADD COLUMN assigner_id BIGINT UNSIGNED NULL COMMENT '实际分配操作人ID' AFTER owner_name,
    ADD COLUMN assigner_name VARCHAR(100) NULL COMMENT '实际分配操作人名称快照' AFTER assigner_id,
    ADD COLUMN assigned_at DATETIME NULL COMMENT '实际分配时间' AFTER assigner_name,
    ADD KEY idx_biz_task_assigner (assigner_id, deleted_at);
