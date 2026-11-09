-- 表单分组与业务字段使用同一有序 schema；分组不产生申请值，仅用于分类展示。
-- 库存型资源的渠道也纳入表单设计，申请页不再额外拼接固定“申请归属”区域。
UPDATE media_approval_config
SET form_schema = JSON_ARRAY_INSERT(
        form_schema,
        '$[0]', JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full','helpText','资源库存按渠道隔离，请先明确本次申请的渠道归属。'),
        '$[1]', JSON_OBJECT('key','channelId','label','所属渠道','type','select','required',true,'width','half','optionSource','channels','placeholder','请选择系统渠道','helpText','资源库存按渠道隔离，审批通过后仅能分配该渠道下的资产。'),
        '$[2]', JSON_OBJECT('key','sectionDetails','label',IF(asset_type = 'PIXEL','像素信息','申请详情'),'type','section','required',false,'width','full')
    )
WHERE asset_type IN ('PERSONAL','BM','PIXEL','TG')
  AND deleted_at = 0
  AND JSON_SEARCH(form_schema, 'one', 'sectionOwnership', NULL, '$[*].key') IS NULL;

UPDATE media_approval_config
SET form_schema = JSON_ARRAY_INSERT(
        form_schema,
        '$[0]', JSON_OBJECT(
            'key','sectionDetails',
            'label',IF(asset_type = 'BUNDLE','绑包信息','主页信息'),
            'type','section','required',false,'width','full'
        )
    )
WHERE asset_type IN ('BUNDLE','PAGE')
  AND deleted_at = 0
  AND JSON_SEARCH(form_schema, 'one', 'sectionDetails', NULL, '$[*].key') IS NULL;

UPDATE media_approval_config
SET form_schema = JSON_ARRAY(
        JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full'),
        JSON_OBJECT('key','departmentId','label','所属部门','type','select','required',true,'width','half','optionSource','departments','placeholder','请选择系统部门'),
        JSON_OBJECT('key','assigneeId','label','使用人','type','select','required',true,'width','half','optionSource','users','placeholder','请选择系统人员'),
        JSON_OBJECT('key','projectId','label','所属项目','type','select','required',false,'width','half','optionSource','projects','placeholder','请选择系统项目'),
        JSON_OBJECT('key','sectionDetails','label',CASE asset_type WHEN 'COMPUTER' THEN '电脑信息' WHEN 'MOBILE' THEN '手机信息' WHEN 'STATIC_IP' THEN '静态 IP 信息' ELSE '邮箱信息' END,'type','section','required',false,'width','full'),
        JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
        JSON_OBJECT('key','purpose','label','用途说明','type','textarea','required',true,'width','full','placeholder',CASE asset_type WHEN 'COMPUTER' THEN '请说明电脑用途及配置要求' WHEN 'MOBILE' THEN '请说明手机用途及配置要求' WHEN 'STATIC_IP' THEN '请说明静态 IP 用途及配置要求' ELSE '请说明邮箱用途及配置要求' END,'maxLength',200)
    )
WHERE asset_type IN ('COMPUTER','MOBILE','STATIC_IP','EMAIL')
  AND deleted_at = 0;

UPDATE media_approval_config
SET form_schema = JSON_ARRAY_INSERT(
        form_schema,
        '$[0]', JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full'),
        '$[3]', JSON_OBJECT('key','sectionPayment','label','付款信息','type','section','required',false,'width','full')
    )
WHERE asset_type = 'PAYMENT'
  AND deleted_at = 0
  AND JSON_SEARCH(form_schema, 'one', 'sectionOwnership', NULL, '$[*].key') IS NULL;

UPDATE media_approval_config
SET form_schema = JSON_ARRAY_INSERT(
        form_schema,
        '$[0]', JSON_OBJECT('key','sectionOperation','label','操作信息','type','section','required',false,'width','full')
    )
WHERE asset_type = 'ACCOUNT_OPERATION'
  AND deleted_at = 0
  AND JSON_SEARCH(form_schema, 'one', 'sectionOperation', NULL, '$[*].key') IS NULL;
