UPDATE ad_account_asset
SET account_name = ''
WHERE account_name IS NULL;

ALTER TABLE ad_account_asset
    MODIFY account_name VARCHAR(255) NOT NULL DEFAULT ''
        COMMENT '广告账户名称快照；仅由 MongoDB fb_ad_accounts 同步更新，页面和导入禁止修改',
    ADD COLUMN account_status INT NULL
        COMMENT 'Facebook 平台账户状态；仅由 MongoDB fb_ad_accounts 同步更新'
        AFTER account_name,
    ADD COLUMN channel_id BIGINT UNSIGNED NULL
        COMMENT '所属渠道 ID；逻辑关联 media_channel.id，不建立数据库外键'
        AFTER account_attribute,
    ADD COLUMN channel_name VARCHAR(255) NULL
        COMMENT '所属渠道名称快照；渠道改名时同步更新'
        AFTER channel_id,
    ADD COLUMN is_manually_updated TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '是否已人工维护业务资料：0 否，1 是；为 1 时飞书同步不得覆盖业务字段'
        AFTER is_limited,
    ADD COLUMN manually_updated_at DATETIME(3) NULL
        COMMENT '最近一次人工编辑或表格导入时间（UTC）'
        AFTER is_manually_updated,
    ADD COLUMN manually_updated_by BIGINT UNSIGNED NULL
        COMMENT '最近一次人工维护用户 ID；逻辑关联 sys_user.id'
        AFTER manually_updated_at,
    ADD COLUMN last_mongo_sync_at DATETIME(3) NULL
        COMMENT '最近一次从 MongoDB fb_ad_accounts 同步名称和平台状态的时间（UTC）'
        AFTER manually_updated_by,
    ADD COLUMN last_feishu_sync_at DATETIME(3) NULL
        COMMENT '最近一次从 feishu_account_used_record 同步业务资料的时间（UTC）'
        AFTER last_mongo_sync_at;

ALTER TABLE ad_account_asset
    DROP INDEX uk_ad_account_asset_account_deleted,
    ADD UNIQUE KEY uk_ad_account_asset_identity_deleted
        (account_id, account_name, deleted_at),
    ADD KEY idx_ad_account_asset_account_id (account_id, deleted_at),
    ADD KEY idx_ad_account_asset_channel_name (channel_name, deleted_at),
    ADD KEY idx_ad_account_asset_manual_sync
        (is_manually_updated, last_feishu_sync_at, id);

CREATE TABLE ad_account_asset_assignment (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '广告账户使用人分配记录 ID',
    ad_account_asset_id BIGINT UNSIGNED NOT NULL
        COMMENT '广告账户资产 ID；逻辑关联 ad_account_asset.id，不建立数据库外键',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '使用人 ID；逻辑关联 sys_user.id',
    user_name VARCHAR(100) NULL COMMENT '使用人名称快照，用于跨服务稳定展示',
    is_primary TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否主使用人：0 否，1 是',
    assignment_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        COMMENT '分配状态：ACTIVE 使用中，RELEASED 已解除',
    assignment_source VARCHAR(30) NOT NULL
        COMMENT '分配来源：APPLICATION 申请办理，MANUAL 人工分配，IMPORT 表格导入，MIGRATION 历史迁移',
    application_id BIGINT UNSIGNED NULL COMMENT '来源申请单 ID；逻辑关联 system 服务申请记录',
    assigned_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        COMMENT '开始使用时间（UTC）',
    released_at DATETIME(3) NULL COMMENT '解除使用时间（UTC）',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人用户 ID',
    updated_by BIGINT UNSIGNED NULL COMMENT '最后更新人用户 ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        COMMENT '记录创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0
        COMMENT '软删除时间戳；0 表示有效，非 0 表示已删除',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ad_account_assignment_user_deleted
        (ad_account_asset_id, user_id, deleted_at),
    KEY idx_ad_account_assignment_user_status
        (user_id, assignment_status, deleted_at),
    KEY idx_ad_account_assignment_asset_status
        (ad_account_asset_id, assignment_status, deleted_at),
    KEY idx_ad_account_assignment_application (application_id, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '广告账户与使用人的多对多分配关系；解除时保留历史记录';

-- 历史账户和使用人关系先复制到新台账；旧表继续保留给灰度期的财务与兼容查询。
INSERT INTO ad_account_asset (
    account_id,
    account_name,
    account_type,
    channel_id,
    channel_name,
    update_source,
    created_by,
    updated_by
)
SELECT
    COALESCE(NULLIF(account.fb_account_id, ''), account.account_id),
    COALESCE(account.account_name, ''),
    account.account_type,
    account.channel_id,
    channel.channel_name,
    'MIGRATION',
    account.created_by,
    account.updated_by
FROM media_channel_account account
LEFT JOIN media_channel channel
    ON channel.id = account.channel_id
   AND channel.deleted_at = 0
WHERE account.deleted_at = 0
ON DUPLICATE KEY UPDATE
    channel_id = COALESCE(ad_account_asset.channel_id, VALUES(channel_id)),
    channel_name = COALESCE(ad_account_asset.channel_name, VALUES(channel_name));

INSERT INTO ad_account_asset_assignment (
    ad_account_asset_id,
    user_id,
    user_name,
    is_primary,
    assignment_status,
    assignment_source,
    application_id,
    assigned_at,
    created_by,
    updated_by
)
SELECT
    asset.id,
    assignment.assignee_id,
    assignment.assignee_name,
    CASE WHEN account.operator_id = assignment.assignee_id THEN 1 ELSE 0 END,
    'ACTIVE',
    'MIGRATION',
    assignment.application_id,
    assignment.assigned_at,
    assignment.assigned_by,
    assignment.assigned_by
FROM media_channel_account_assignment assignment
JOIN media_channel_account account
    ON account.account_id = assignment.account_id
   AND account.channel_id = assignment.channel_id
   AND account.deleted_at = 0
JOIN ad_account_asset asset
    ON asset.account_id = COALESCE(NULLIF(account.fb_account_id, ''), account.account_id)
   AND asset.account_name = COALESCE(account.account_name, '')
   AND asset.deleted_at = 0
WHERE assignment.deleted_at = 0
ON DUPLICATE KEY UPDATE
    assignment_status = 'ACTIVE',
    released_at = NULL,
    updated_by = VALUES(updated_by);
