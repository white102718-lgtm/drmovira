CREATE TABLE media_asset_application_comment (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '流程评论主键',
    application_id BIGINT UNSIGNED NOT NULL COMMENT '资产申请 ID，逻辑关联 media_asset_application.id',
    actor_id BIGINT UNSIGNED NOT NULL COMMENT '评论人用户 ID，逻辑关联 sys_user.id',
    actor_name VARCHAR(100) NOT NULL COMMENT '评论时固化的评论人名称',
    actor_role VARCHAR(40) NOT NULL COMMENT '评论人在流程中的身份：申请人、审批人、办理人或抄送人',
    content VARCHAR(500) NOT NULL COMMENT '评论正文',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '评论时间',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建人用户 ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后更新人用户 ID',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳，0 表示有效',
    PRIMARY KEY (id),
    KEY idx_asset_application_comment_application (application_id, deleted_at, created_at, id),
    KEY idx_asset_application_comment_actor (actor_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='资产申请流程评论';
