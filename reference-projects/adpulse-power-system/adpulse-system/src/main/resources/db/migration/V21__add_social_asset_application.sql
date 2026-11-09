-- 社交资产使用一张审批配置申请 TG号、微信号和 Facebook 账号。
-- 类型与数量为必填；地区和说明用于辅助办理，不阻塞提交。
UPDATE media_approval_config
SET category = 'social',
    flow_name = '社交资产申请',
    description = '申请 TG号、微信号或 Facebook 账号，审批完成后由办理人分配对应类型库存。',
    icon = 'lucide:messages-square',
    form_schema = JSON_ARRAY(
        JSON_OBJECT('key','sectionDetails','label','社交资产信息','type','section','required',false,'width','full'),
        JSON_OBJECT('key','socialAssetType','label','社交资产类型','type','select','required',true,'width','half','optionSource','custom','placeholder','请选择社交资产类型','options',JSON_ARRAY('TG号','微信号','Facebook 账号')),
        JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
        JSON_OBJECT('key','region','label','地区','type','select','required',false,'width','half','optionSource','custom','placeholder','请选择地区','options',JSON_ARRAY('新加坡','马来西亚','泰国','越南','印度尼西亚','菲律宾','印度','美国','日本','香港')),
        JSON_OBJECT('key','purpose','label','说明','type','textarea','required',false,'width','full','placeholder','请输入使用说明','maxLength',200)
    ),
    settings = JSON_SET(
        COALESCE(settings, JSON_OBJECT()),
        '$.handlerAction',
        JSON_OBJECT(
            'resourceAssignment', JSON_OBJECT(
                'assetTypeSource', 'application',
                'assetTypeFieldKey', 'socialAssetType',
                'channelFieldKey', '',
                'enabled', TRUE,
                'quantityFieldKey', 'quantity'
            )
        )
    ),
    nodes = JSON_SET(
        nodes,
        CONCAT('$[', JSON_LENGTH(nodes) - 1, '].handlerAction'),
        JSON_OBJECT(
            'resourceAssignment', JSON_OBJECT(
                'assetTypeSource', 'application',
                'assetTypeFieldKey', 'socialAssetType',
                'channelFieldKey', '',
                'enabled', TRUE,
                'quantityFieldKey', 'quantity'
            )
        )
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE asset_type = 'TG'
  AND deleted_at = 0
  AND JSON_LENGTH(nodes) > 0;
