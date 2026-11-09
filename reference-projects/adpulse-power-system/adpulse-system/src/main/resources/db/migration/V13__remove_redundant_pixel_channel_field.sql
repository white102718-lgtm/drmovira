-- 像素申请的渠道改由申请基本信息统一选择，低代码表单不再重复维护渠道文本字段。
-- 仅更新后续申请使用的审批配置；历史申请的表单快照保持不变，便于审计追溯。
UPDATE media_approval_config
SET form_schema = JSON_REMOVE(
        form_schema,
        REPLACE(
            JSON_UNQUOTE(JSON_SEARCH(form_schema, 'one', 'channel', NULL, '$[*].key')),
            '.key',
            ''
        )
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE asset_type = 'PIXEL'
  AND deleted_at = 0
  AND JSON_SEARCH(form_schema, 'one', 'channel', NULL, '$[*].key') IS NOT NULL;
