-- 广告账户允许多人使用；分配关系单独留痕，不能再用渠道账户主表的一对一使用人字段覆盖历史分配。
CREATE TABLE media_channel_account_assignment (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '广告账户共享分配关系主键',
    channel_id BIGINT UNSIGNED NOT NULL COMMENT '渠道 ID 快照，逻辑关联 media_channel.id',
    account_id VARCHAR(100) NOT NULL COMMENT '广告账户 ID，逻辑关联 media_channel_account.account_id',
    application_id BIGINT UNSIGNED NOT NULL COMMENT '广告户申请 ID，逻辑关联 media_asset_application.id',
    assignee_id BIGINT UNSIGNED NOT NULL COMMENT '实际使用人 ID，逻辑关联 sys_user.id',
    assignee_name VARCHAR(100) NOT NULL COMMENT '分配时固化的使用人名称',
    assigned_by BIGINT UNSIGNED NOT NULL COMMENT '办理人 ID，逻辑关联 sys_user.id',
    assigned_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '分配时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_channel_account_assignment_active (account_id, application_id, assignee_id, deleted_at),
    KEY idx_channel_account_assignment_account (account_id, deleted_at),
    KEY idx_channel_account_assignment_application (application_id, deleted_at),
    KEY idx_channel_account_assignment_assignee (assignee_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='广告账户共享分配关系';
