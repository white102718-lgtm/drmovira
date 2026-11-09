-- 广告账户操作必须引用账号管理中的稳定账户 ID，避免申请人手工输入无效或重复 ID。
-- 仅定点修改 accountIds 字段，保留管理员已经配置的其他字段与审批节点。
UPDATE media_approval_config
SET form_schema = JSON_REMOVE(
        JSON_SET(
            form_schema,
            REPLACE(
                JSON_UNQUOTE(JSON_SEARCH(form_schema, 'one', 'accountIds', NULL, '$[*].key')),
                '.key', '.label'
            ), '广告账户',
            REPLACE(
                JSON_UNQUOTE(JSON_SEARCH(form_schema, 'one', 'accountIds', NULL, '$[*].key')),
                '.key', '.type'
            ), 'multi-select',
            REPLACE(
                JSON_UNQUOTE(JSON_SEARCH(form_schema, 'one', 'accountIds', NULL, '$[*].key')),
                '.key', '.optionSource'
            ), 'ad-accounts',
            REPLACE(
                JSON_UNQUOTE(JSON_SEARCH(form_schema, 'one', 'accountIds', NULL, '$[*].key')),
                '.key', '.placeholder'
            ), '请选择系统账户管理中的广告账户',
            REPLACE(
                JSON_UNQUOTE(JSON_SEARCH(form_schema, 'one', 'accountIds', NULL, '$[*].key')),
                '.key', '.width'
            ), 'full'
        ),
        REPLACE(
            JSON_UNQUOTE(JSON_SEARCH(form_schema, 'one', 'accountIds', NULL, '$[*].key')),
            '.key', '.validationRule'
        ),
        REPLACE(
            JSON_UNQUOTE(JSON_SEARCH(form_schema, 'one', 'accountIds', NULL, '$[*].key')),
            '.key', '.options'
        )
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE asset_type = 'ACCOUNT_OPERATION'
  AND deleted_at = 0
  AND JSON_SEARCH(form_schema, 'one', 'accountIds', NULL, '$[*].key') IS NOT NULL;
