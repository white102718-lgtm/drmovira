-- Complete the MPower pixel application rules in the low-code schema.
UPDATE media_approval_config
SET form_schema = JSON_ARRAY(
      JSON_OBJECT('key','pixelNames','label','像素','type','textarea','required',true,
                  'placeholder','请输入“像素名称:像素ID”，多个像素以“;”分隔','validationRule','pixel-list'),
      JSON_OBJECT('key','bms','label','BM ID','type','text','required',true,
                  'placeholder','请输入 BM ID，多个以“;”分隔','validationRule','digit-list'),
      JSON_OBJECT('key','channel','label','渠道','type','text','required',true,
                  'placeholder','请输入渠道名称'),
      JSON_OBJECT('key','accountIds','label','授权账户 ID','type','textarea','required',true,
                  'placeholder','请输入授权账户 ID，多个以“;”分隔','validationRule','digit-list')
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE asset_type = 'PIXEL' AND deleted_at = 0;
