-- 人工审核并执行。控制项目钱包供应方：0=旧MPower代理创建，1=新系统直连Safeheron。
-- 保留且仅保留一个启用项；项目请求中的createWallet仍决定本次是否需要创建钱包。
START TRANSACTION;

INSERT INTO sys_dict_type (dict_code, dict_name, status, remark)
SELECT 'PROJECT_CREATE_WALLET', '项目钱包创建方式', 1,
       '启用且仅启用一个字典项：0=旧MPower代理创建，1=新系统直连Safeheron'
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_type
    WHERE dict_code = 'PROJECT_CREATE_WALLET' AND deleted_at = 0
);

INSERT INTO sys_dict_item (dict_type_id, item_value, item_label, sort_order, status, remark)
SELECT type.id, '0', '旧MPower代理创建', 0, 1,
       '生产未配置Safeheron凭证时，通过旧MPower幂等创建并同步钱包'
FROM sys_dict_type type
WHERE type.dict_code = 'PROJECT_CREATE_WALLET'
  AND type.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1 FROM sys_dict_item item
      WHERE item.dict_type_id = type.id AND item.deleted_at = 0
  );

COMMIT;
