-- 广告户申请必须先选择开户渠道；渠道选项由前端受控数据源实时读取，配置中只保存数据源标识。
UPDATE media_approval_config
SET form_schema = JSON_ARRAY_INSERT(
        form_schema,
        '$[1]',
        JSON_OBJECT(
            'key', 'channelId',
            'label', '渠道',
            'type', 'select',
            'required', true,
            'width', 'half',
            'optionSource', 'channels',
            'placeholder', '请选择渠道'
        )
    ),
    description = '沿用 MPower 渠道、账户名称、开户数量、授权方式、充值金额、时区与备注字段。'
WHERE asset_type = 'ACCOUNT_OPENING'
  AND deleted_at = 0
  AND JSON_SEARCH(form_schema, 'one', 'channelId', NULL, '$[*].key') IS NULL;

UPDATE media_application_definition
SET description = '选择渠道后申请广告户，并填写授权方式、开户数量、首充与时区。'
WHERE application_code = 'ACCOUNT_OPENING'
  AND deleted_at = 0;
