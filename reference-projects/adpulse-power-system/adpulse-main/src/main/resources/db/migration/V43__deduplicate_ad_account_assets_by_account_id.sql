-- 账户 ID 是广告账户的稳定业务标识；账户名称可能随平台同步变更，不能参与唯一性判定。
-- 迁移期间按人工维护、渠道归属、名称完整度和更新时间选择保留行，并将使用人关系迁回该行。
CREATE TEMPORARY TABLE ad_account_asset_deduplication_map AS
SELECT
    duplicate_asset.id AS duplicate_asset_id,
    canonical_asset.id AS canonical_asset_id
FROM ad_account_asset duplicate_asset
JOIN (
    SELECT account_id, id
    FROM (
        SELECT
            asset.account_id,
            asset.id,
            ROW_NUMBER() OVER (
                PARTITION BY asset.account_id
                ORDER BY
                    asset.is_manually_updated DESC,
                    asset.channel_id IS NOT NULL DESC,
                    asset.account_name <> '' DESC,
                    asset.updated_at DESC,
                    asset.id DESC
            ) AS rank_number
        FROM ad_account_asset asset
        WHERE asset.deleted_at = 0
    ) ranked_asset
    WHERE rank_number = 1
) canonical_asset
    ON canonical_asset.account_id = duplicate_asset.account_id
WHERE duplicate_asset.deleted_at = 0
  AND duplicate_asset.id <> canonical_asset.id;

ALTER TABLE ad_account_asset_deduplication_map
    ADD PRIMARY KEY (duplicate_asset_id),
    ADD KEY idx_ad_account_asset_deduplication_canonical (canonical_asset_id);

-- 使用人关系以账户 ID 为维度保留；发生冲突时保留既有关系并合并活动状态与可追溯来源。
INSERT INTO ad_account_asset_assignment (
    ad_account_asset_id,
    user_id,
    user_name,
    is_primary,
    assignment_status,
    assignment_source,
    application_id,
    assigned_at,
    released_at,
    created_by,
    updated_by,
    deleted_at
)
SELECT
    mapping.canonical_asset_id,
    assignment.user_id,
    assignment.user_name,
    assignment.is_primary,
    assignment.assignment_status,
    assignment.assignment_source,
    assignment.application_id,
    assignment.assigned_at,
    assignment.released_at,
    assignment.created_by,
    assignment.updated_by,
    assignment.deleted_at
FROM ad_account_asset_assignment assignment
JOIN ad_account_asset_deduplication_map mapping
    ON mapping.duplicate_asset_id = assignment.ad_account_asset_id
ON DUPLICATE KEY UPDATE
    user_name = COALESCE(VALUES(user_name), ad_account_asset_assignment.user_name),
    is_primary = GREATEST(ad_account_asset_assignment.is_primary, VALUES(is_primary)),
    assignment_status = CASE
        WHEN ad_account_asset_assignment.assignment_status = 'ACTIVE'
            OR VALUES(assignment_status) = 'ACTIVE' THEN 'ACTIVE'
        ELSE ad_account_asset_assignment.assignment_status
    END,
    assignment_source = VALUES(assignment_source),
    application_id = COALESCE(VALUES(application_id), ad_account_asset_assignment.application_id),
    assigned_at = LEAST(ad_account_asset_assignment.assigned_at, VALUES(assigned_at)),
    released_at = CASE
        WHEN ad_account_asset_assignment.assignment_status = 'ACTIVE'
            OR VALUES(assignment_status) = 'ACTIVE' THEN NULL
        ELSE COALESCE(ad_account_asset_assignment.released_at, VALUES(released_at))
    END,
    updated_by = VALUES(updated_by),
    updated_at = CURRENT_TIMESTAMP(3);

DELETE assignment
FROM ad_account_asset_assignment assignment
JOIN ad_account_asset_deduplication_map mapping
    ON mapping.duplicate_asset_id = assignment.ad_account_asset_id;

DELETE duplicate_asset
FROM ad_account_asset duplicate_asset
JOIN ad_account_asset_deduplication_map mapping
    ON mapping.duplicate_asset_id = duplicate_asset.id;

DROP TEMPORARY TABLE ad_account_asset_deduplication_map;

ALTER TABLE ad_account_asset
    DROP INDEX uk_ad_account_asset_identity_deleted,
    ADD UNIQUE KEY uk_ad_account_asset_account_deleted
        (account_id, deleted_at);
