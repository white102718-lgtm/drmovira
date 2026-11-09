-- 由用户审核后在部署前手工执行。0表示旧MPower代理创建，1表示新系统直连Safeheron。
UPDATE sys_dict_type
SET dict_name = '项目钱包创建方式',
    remark = '启用且仅启用一个字典项：0=旧MPower代理创建，1=新系统直连Safeheron'
WHERE dict_code = 'PROJECT_CREATE_WALLET'
  AND deleted_at = 0;

UPDATE sys_dict_item item
INNER JOIN sys_dict_type type
    ON type.id = item.dict_type_id
    AND type.dict_code = 'PROJECT_CREATE_WALLET'
    AND type.deleted_at = 0
SET item.item_label = CASE item.item_value
        WHEN '0' THEN '旧MPower代理创建'
        WHEN '1' THEN '新系统直连Safeheron'
        ELSE item.item_label
    END,
    item.remark = CASE item.item_value
        WHEN '0' THEN '生产未配置Safeheron凭证时，通过旧MPower幂等创建并同步钱包'
        WHEN '1' THEN '由新系统使用本地Safeheron团队凭证直接创建钱包'
        ELSE item.remark
    END
WHERE item.deleted_at = 0
  AND item.item_value IN ('0', '1');
