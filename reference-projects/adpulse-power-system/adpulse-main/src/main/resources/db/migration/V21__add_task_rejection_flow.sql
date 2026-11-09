ALTER TABLE biz_task
    ADD COLUMN rejected_at DATETIME(3) NULL COMMENT '负责人驳回任务时间，UTC' AFTER withdraw_reason,
    ADD COLUMN rejected_by BIGINT UNSIGNED NULL COMMENT '驳回任务的负责人用户ID' AFTER rejected_at,
    ADD COLUMN rejection_reason VARCHAR(500) NULL COMMENT '负责人驳回任务原因' AFTER rejected_by;

ALTER TABLE biz_task DROP CHECK ck_biz_task_status;
ALTER TABLE biz_task
    ADD CONSTRAINT ck_biz_task_status CHECK (
        status IN (
            'PENDING_ASSIGNMENT', 'PENDING_CONFIRMATION', 'PROCESSING',
            'PENDING_ACCEPTANCE', 'COMPLETED', 'WITHDRAWN', 'REJECTED'
        )
    );
