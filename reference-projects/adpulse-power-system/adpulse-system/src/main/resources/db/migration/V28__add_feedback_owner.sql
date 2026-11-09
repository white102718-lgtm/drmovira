ALTER TABLE sys_feedback
    ADD COLUMN owner_id BIGINT UNSIGNED NULL
        COMMENT '当前负责人ID，逻辑关联启用的sys_user.id；为空表示未分配'
        AFTER admin_reply,
    ADD COLUMN owner_name VARCHAR(100) NULL
        COMMENT '当前负责人显示名称快照，负责人改名后在下次分配时更新'
        AFTER owner_id,
    ADD KEY idx_feedback_owner_time (owner_id, updated_at, deleted_at);
