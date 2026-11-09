ALTER TABLE ad_account_asset
    ADD COLUMN inventory_status VARCHAR(24) NOT NULL DEFAULT 'AVAILABLE'
        COMMENT '库存状态：AVAILABLE 可用，ASSIGNED 已分配，RETURN_PENDING 待回收，DISABLED 已停用'
        AFTER account_status,
    ADD KEY idx_ad_account_asset_inventory_status
        (inventory_status, deleted_at, id);

-- 旧库存中存在、但尚未进入统一账户资产台账的广告账户也必须保留。
INSERT INTO ad_account_asset (
    account_id,
    account_name,
    inventory_status,
    update_source,
    created_by,
    updated_by
)
SELECT
    asset.asset_code,
    COALESCE(asset.asset_name, ''),
    CASE
        WHEN asset.status IN ('AVAILABLE', 'ASSIGNED', 'RETURN_PENDING', 'DISABLED')
            THEN asset.status
        ELSE 'AVAILABLE'
    END,
    'INVENTORY_MIGRATION',
    asset.created_by,
    asset.updated_by
FROM media_asset asset
WHERE asset.asset_type = 'AD_ACCOUNT'
  AND asset.deleted_at = 0
ON DUPLICATE KEY UPDATE
    inventory_status = VALUES(inventory_status),
    updated_by = VALUES(updated_by),
    updated_at = CURRENT_TIMESTAMP(3);

-- 对名称曾变化而未命中联合唯一键的账户，按稳定账户 ID 继承旧库存状态。
UPDATE ad_account_asset target
JOIN media_asset legacy
    ON legacy.asset_type = 'AD_ACCOUNT'
   AND legacy.asset_code = target.account_id
   AND legacy.deleted_at = 0
SET target.inventory_status = CASE
        WHEN legacy.status IN ('AVAILABLE', 'ASSIGNED', 'RETURN_PENDING', 'DISABLED')
            THEN legacy.status
        ELSE 'AVAILABLE'
    END
WHERE target.deleted_at = 0;

-- 有有效使用人关系的账户以新关系表为准，确保状态与实际分配一致。
UPDATE ad_account_asset target
SET target.inventory_status = 'ASSIGNED'
WHERE target.deleted_at = 0
  AND EXISTS (
      SELECT 1
      FROM ad_account_asset_assignment assignment
      WHERE assignment.ad_account_asset_id = target.id
        AND assignment.assignment_status = 'ACTIVE'
        AND assignment.deleted_at = 0
  );
