-- 申请表只保留申请人在 MPower 发起申请时实际填写的内容。
-- 资源所属渠道属于后续库存分配信息，不再强制放入个号、BM 和 TG 申请表。
UPDATE media_approval_config
SET description = CASE asset_type
        WHEN 'PERSONAL' THEN '沿用 MPower 个号申请字段，并支持配置地区选项。'
        WHEN 'BM' THEN '沿用 MPower BM 申请字段，并支持配置地区选项。'
        ELSE '沿用 MPower TG 申请字段，并支持配置地区选项。'
    END,
    form_schema = JSON_ARRAY(
        JSON_OBJECT('key','sectionDetails','label','申请详情','type','section','required',false,'width','full'),
        JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
        JSON_OBJECT('key','region','label','地区','type','select','required',false,'width','half','optionSource','custom','placeholder','请选择地区','options',JSON_ARRAY('新加坡','马来西亚','泰国','越南','印度尼西亚','菲律宾','印度','美国','日本','香港')),
        JSON_OBJECT('key','purpose','label','说明','type','text','required',false,'width','half','placeholder','请输入说明','maxLength',200)
    )
WHERE asset_type IN ('PERSONAL','BM','TG')
  AND deleted_at = 0;

UPDATE media_approval_config
SET description = '沿用 MPower 像素、BM、渠道和授权账户字段。',
    form_schema = JSON_ARRAY(
        JSON_OBJECT('key','sectionDetails','label','像素信息','type','section','required',false,'width','full'),
        JSON_OBJECT('key','pixelNames','label','像素','type','textarea','required',true,'width','full','placeholder','请输入“像素名称:像素ID”，多个像素以“;”分隔','validationRule','pixel-list'),
        JSON_OBJECT('key','bms','label','BM ID','type','text','required',true,'width','half','placeholder','请输入 BM ID，多个以“;”分隔','validationRule','digit-list'),
        JSON_OBJECT('key','channel','label','渠道','type','text','required',true,'width','half','placeholder','请输入渠道名称','maxLength',50),
        JSON_OBJECT('key','accountIds','label','授权账户 ID','type','textarea','required',true,'width','full','placeholder','请输入授权账户 ID，多个以“;”分隔','validationRule','digit-list')
    )
WHERE asset_type = 'PIXEL'
  AND deleted_at = 0;

UPDATE media_approval_config
SET description = '沿用 MPower 手机号申请字段；用途选项可在表单设计中维护。',
    form_schema = JSON_ARRAY(
        JSON_OBJECT('key','sectionDetails','label','手机信息','type','section','required',false,'width','full'),
        JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
        JSON_OBJECT('key','region','label','地区','type','select','required',false,'width','half','optionSource','custom','placeholder','请选择地区','options',JSON_ARRAY('新加坡','马来西亚','泰国','越南','印度尼西亚','菲律宾','印度','美国','日本','香港')),
        JSON_OBJECT('key','purpose','label','用途','type','select','required',true,'width','half','optionSource','custom','placeholder','请选择用途','options',JSON_ARRAY('FB开发者验证','谷歌验证','FB个号验证','其它'))
    )
WHERE asset_type = 'MOBILE'
  AND deleted_at = 0;

UPDATE media_approval_config
SET description = '沿用 MPower 静态 IP 申请字段，并支持配置地区选项。',
    form_schema = JSON_ARRAY(
        JSON_OBJECT('key','sectionDetails','label','静态 IP 信息','type','section','required',false,'width','full'),
        JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
        JSON_OBJECT('key','region','label','地区','type','select','required',false,'width','half','optionSource','custom','placeholder','请选择地区','options',JSON_ARRAY('新加坡','马来西亚','泰国','越南','印度尼西亚','菲律宾','印度','美国','日本','香港')),
        JSON_OBJECT('key','purpose','label','说明','type','text','required',false,'width','half','placeholder','请输入说明','maxLength',200)
    )
WHERE asset_type = 'STATIC_IP'
  AND deleted_at = 0;

UPDATE media_approval_config
SET description = '沿用 MPower 邮箱申请字段。',
    form_schema = JSON_ARRAY(
        JSON_OBJECT('key','sectionDetails','label','邮箱信息','type','section','required',false,'width','full'),
        JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
        JSON_OBJECT('key','purpose','label','说明','type','text','required',false,'width','half','placeholder','请输入说明','maxLength',200)
    )
WHERE asset_type = 'EMAIL'
  AND deleted_at = 0;

UPDATE media_approval_config
SET description = '沿用 MPower 渠道、备款金额、渠道昨日消耗和备注字段。',
    form_schema = JSON_ARRAY(
        JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full'),
        JSON_OBJECT('key','channelId','label','渠道','type','select','required',true,'width','half','optionSource','channels','placeholder','请选择渠道'),
        JSON_OBJECT('key','sectionPayment','label','付款信息','type','section','required',false,'width','full'),
        JSON_OBJECT('key','amount','label','备款金额','type','number','required',true,'minValue',1,'width','half','validationRule','positive-money'),
        JSON_OBJECT('key','channelYesterdayCost','label','渠道昨日消耗','type','number','required',true,'minValue',0,'width','half'),
        JSON_OBJECT('key','remark','label','备注','type','textarea','required',false,'width','full','placeholder','请输入备注')
    )
WHERE asset_type = 'PAYMENT'
  AND deleted_at = 0;

-- MPower 的账户操作来自多个弹窗；合并后用操作类型控制对应字段显隐和必填。
UPDATE media_approval_config
SET description = '合并 MPower 充值、扣款、清零、回收、解绑和换绑申请，按操作类型显示原表单字段。',
    form_schema = JSON_ARRAY(
        JSON_OBJECT('key','sectionOperation','label','操作信息','type','section','required',false,'width','full'),
        JSON_OBJECT('key','operationType','label','操作类型','type','select','required',true,'width','half','optionSource','custom','options',JSON_ARRAY('充值','扣款','活跃清零','活跃清零回收','回收','解绑','换绑')),
        JSON_OBJECT('key','accountIds','label','广告账户 ID','type','textarea','required',true,'width','full','placeholder','请输入广告账户 ID，多个以“;”分隔','validationRule','digit-list'),
        JSON_OBJECT('key','amount','label','金额','type','number','required',false,'minValue',0.01,'width','half','validationRule','positive-money','visibleWhen',JSON_OBJECT('fieldKey','operationType','operator','in','value',JSON_ARRAY('充值','扣款')),'requiredWhen',JSON_OBJECT('fieldKey','operationType','operator','in','value',JSON_ARRAY('充值','扣款'))),
        JSON_OBJECT('key','applyReason','label','申请原因','type','select','required',false,'width','half','optionSource','custom','options',JSON_ARRAY('项目暂停','账户问题暂停','项目停止','账户不花钱','拒审严重','其它'),'visibleWhen',JSON_OBJECT('fieldKey','operationType','operator','in','value',JSON_ARRAY('活跃清零','活跃清零回收')),'requiredWhen',JSON_OBJECT('fieldKey','operationType','operator','in','value',JSON_ARRAY('活跃清零','活跃清零回收'))),
        JSON_OBJECT('key','originalAuthAccount','label','原解绑邮箱/BM','type','text','required',false,'width','half','placeholder','请输入原解绑邮箱/BM','visibleWhen',JSON_OBJECT('fieldKey','operationType','operator','equals','value','换绑'),'requiredWhen',JSON_OBJECT('fieldKey','operationType','operator','equals','value','换绑')),
        JSON_OBJECT('key','authAccount','label','解绑/换绑邮箱或 BM','type','text','required',false,'width','half','placeholder','请输入邮箱或 BM','visibleWhen',JSON_OBJECT('fieldKey','operationType','operator','in','value',JSON_ARRAY('解绑','换绑')),'requiredWhen',JSON_OBJECT('fieldKey','operationType','operator','in','value',JSON_ARRAY('解绑','换绑'))),
        JSON_OBJECT('key','remark','label','备注','type','textarea','required',false,'width','full','placeholder','请输入备注','maxLength',100,'visibleWhen',JSON_OBJECT('fieldKey','operationType','operator','in','value',JSON_ARRAY('活跃清零','活跃清零回收','回收')),'requiredWhen',JSON_OBJECT('fieldKey','operationType','operator','equals','value','回收'))
    )
WHERE asset_type = 'ACCOUNT_OPERATION'
  AND deleted_at = 0;
