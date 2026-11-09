-- 人工审核并执行。默认开启飞书广告账户资料同步；仅启用值 0 会暂停同步。
-- 未配置、禁用或删除字典类型/字典项时保持原有同步行为，避免部署遗漏导致数据停止更新。
START TRANSACTION;

INSERT INTO sys_dict_type (dict_code, dict_name, status, remark)
SELECT
    'AD_ACCOUNT_ASSET_FEISHU_SYNC',
    '广告账户飞书资料同步开关',
    1,
    '启用字典项值为0时暂停从feishu_account_used_record同步业务资料；未配置时默认开启'
WHERE NOT EXISTS (
    SELECT 1
    FROM sys_dict_type
    WHERE dict_code = 'AD_ACCOUNT_ASSET_FEISHU_SYNC'
      AND deleted_at = 0
);

INSERT INTO sys_dict_item (
    dict_type_id,
    item_value,
    item_label,
    sort_order,
    status,
    remark
)
SELECT
    type.id,
    '1',
    '开启同步',
    0,
    1,
    '修改为0可暂停飞书广告账户资料同步；请勿同时配置多个启用项'
FROM sys_dict_type type
WHERE type.dict_code = 'AD_ACCOUNT_ASSET_FEISHU_SYNC'
  AND type.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1
      FROM sys_dict_item item
      WHERE item.dict_type_id = type.id
        AND item.deleted_at = 0
  );

COMMIT;
