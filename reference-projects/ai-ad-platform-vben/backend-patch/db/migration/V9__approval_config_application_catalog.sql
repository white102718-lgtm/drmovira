-- Approval configurations are dynamic catalog entries. The internal asset_type is
-- retained only as a stable key and is never selected by business users.
ALTER TABLE media_approval_config
  ADD COLUMN category VARCHAR(24) NOT NULL DEFAULT 'advertising' AFTER asset_type;

UPDATE media_approval_config
SET category = 'advertising'
WHERE asset_type IN ('PERSONAL', 'BM', 'PIXEL', 'TG');

-- Remove unpublished hard-coded examples from an interrupted pre-release, if any.
DELETE FROM media_approval_config
WHERE asset_type IN ('COMPUTER', 'MOBILE', 'PAYMENT');

-- Align the four existing forms with the MPower legacy application forms while
-- preserving their configured approvers, handlers and CC recipients.
UPDATE media_approval_config
SET flow_name = '个号申请',
    form_schema = JSON_ARRAY(
      JSON_OBJECT('key','quantity','label','数量','type','number','required',true),
      JSON_OBJECT('key','region','label','地区','type','select','required',false,
                  'options',JSON_ARRAY('新加坡','马来西亚','泰国','越南','印度尼西亚','菲律宾','印度','美国','日本','香港')),
      JSON_OBJECT('key','purpose','label','说明','type','text','required',false,
                  'placeholder','请输入说明','maxLength',200)
    )
WHERE asset_type = 'PERSONAL' AND deleted_at = 0;

UPDATE media_approval_config
SET flow_name = 'BM 申请',
    form_schema = JSON_ARRAY(
      JSON_OBJECT('key','quantity','label','数量','type','number','required',true),
      JSON_OBJECT('key','region','label','地区','type','select','required',false,
                  'options',JSON_ARRAY('新加坡','马来西亚','泰国','越南','印度尼西亚','菲律宾','印度','美国','日本','香港')),
      JSON_OBJECT('key','purpose','label','说明','type','text','required',false,
                  'placeholder','请输入说明','maxLength',200)
    )
WHERE asset_type = 'BM' AND deleted_at = 0;

UPDATE media_approval_config
SET flow_name = '像素申请',
    form_schema = JSON_ARRAY(
      JSON_OBJECT('key','pixelNames','label','像素','type','textarea','required',true,
                  'placeholder','请输入“像素名称:像素ID”，多个像素以“;”分隔','validationRule','pixel-list'),
      JSON_OBJECT('key','bms','label','BM ID','type','text','required',true,
                  'placeholder','请输入BM ID，多个以“;”分隔','validationRule','digit-list'),
      JSON_OBJECT('key','channel','label','渠道','type','text','required',true,
                  'placeholder','请输入渠道名称','maxLength',50),
      JSON_OBJECT('key','accountIds','label','授权账户ID','type','textarea','required',true,
                  'placeholder','请输入授权账户ID，多个以“;”分隔','validationRule','digit-list')
    )
WHERE asset_type = 'PIXEL' AND deleted_at = 0;

UPDATE media_approval_config
SET flow_name = 'TG 申请',
    form_schema = JSON_ARRAY(
      JSON_OBJECT('key','quantity','label','数量','type','number','required',true),
      JSON_OBJECT('key','region','label','地区','type','select','required',false,
                  'options',JSON_ARRAY('新加坡','马来西亚','泰国','越南','印度尼西亚','菲律宾','印度','美国','日本','香港')),
      JSON_OBJECT('key','purpose','label','说明','type','text','required',false,
                  'placeholder','请输入说明','maxLength',200)
    )
WHERE asset_type = 'TG' AND deleted_at = 0;
