-- 办理动作只在办理人节点执行；审批节点仍只负责通过、驳回和审批意见。
ALTER TABLE media_asset_approval_log
    ADD COLUMN action_data JSON NULL COMMENT '办理节点结构化操作结果' AFTER remark;

-- MPower 打款申请选择渠道后回填昨日消耗与收款地址，服务端提交时再次计算并覆盖只读值。
UPDATE media_approval_config
SET description = '沿用 MPower 打款申请字段；渠道昨日消耗和收款地址由渠道联动接口自动回填。',
    form_schema = JSON_ARRAY(
        JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full'),
        JSON_OBJECT('key','channelId','label','渠道','type','select','required',true,'width','half','optionSource','channels','placeholder','请选择渠道'),
        JSON_OBJECT('key','sectionPayment','label','付款信息','type','section','required',false,'width','full'),
        JSON_OBJECT('key','amount','label','备款金额','type','number','required',true,'minValue',0.01,'width','half','validationRule','positive-money'),
        JSON_OBJECT('key','channelYesterdayCost','label','渠道昨日消耗','type','number','required',true,'minValue',0,'width','half','readOnly',true,
            'autoFill',JSON_OBJECT('source','channel-payment-context','triggerFieldKey','channelId','resultKey','channelYesterdayCost')),
        JSON_OBJECT('key','paymentAddress','label','收款地址','type','text','required',true,'width','full','readOnly',true,
            'autoFill',JSON_OBJECT('source','channel-payment-context','triggerFieldKey','channelId','resultKey','paymentAddress')),
        JSON_OBJECT('key','remark','label','备注','type','textarea','required',false,'width','full','placeholder','请输入备注')
    )
WHERE asset_type='PAYMENT' AND deleted_at=0;

-- 个号、BM、像素和 TG 在全部审批通过后，由办理人从同类型库存中选择资源进行分配。
UPDATE media_approval_config
SET settings = JSON_SET(
        COALESCE(settings, JSON_OBJECT()),
        '$.handlerAction',
        JSON_OBJECT(
            'resourceAssignment', JSON_OBJECT(
                'enabled', true,
                'assetTypeSource', 'application',
                'quantityFieldKey', 'quantity',
                'channelFieldKey', 'channelId'
            )
        )
    ),
    nodes = JSON_SET(
        nodes,
        CONCAT('$[', JSON_LENGTH(nodes) - 1, '].handlerAction'),
        JSON_OBJECT(
            'resourceAssignment', JSON_OBJECT(
                'enabled', true,
                'assetTypeSource', 'application',
                'quantityFieldKey', 'quantity',
                'channelFieldKey', 'channelId'
            )
        )
    )
WHERE asset_type IN ('PERSONAL','BM','PIXEL','TG') AND deleted_at=0;

-- 打款由办理人填写实际金额并上传 1 至 3 张水单，审批人不接触该业务操作。
UPDATE media_approval_config
SET settings = JSON_SET(
        COALESCE(settings, JSON_OBJECT()),
        '$.handlerAction',
        JSON_OBJECT(
            'formSchema', JSON_ARRAY(
                JSON_OBJECT('key','actualAmount','label','实际打款金额','type','number','required',true,'minValue',0.01,'width','half','validationRule','positive-money'),
                JSON_OBJECT('key','receiptFileIds','label','水单图片','type','image-upload','required',true,'width','full','accept','image/*','maxCount',3,'maxFileSizeMb',3,'helpText','支持 1 至 3 张图片，单张不超过 3MB')
            )
        )
    ),
    nodes = JSON_SET(
        nodes,
        CONCAT('$[', JSON_LENGTH(nodes) - 1, '].handlerAction'),
        JSON_OBJECT(
            'formSchema', JSON_ARRAY(
                JSON_OBJECT('key','actualAmount','label','实际打款金额','type','number','required',true,'minValue',0.01,'width','half','validationRule','positive-money'),
                JSON_OBJECT('key','receiptFileIds','label','水单图片','type','image-upload','required',true,'width','full','accept','image/*','maxCount',3,'maxFileSizeMb',3,'helpText','支持 1 至 3 张图片，单张不超过 3MB')
            )
        )
    )
WHERE asset_type='PAYMENT' AND deleted_at=0;

-- 其余需要人工落地的申请由办理人登记真实办理结果，后续可在配置页继续扩展办理字段。
UPDATE media_approval_config
SET settings = JSON_SET(
        COALESCE(settings, JSON_OBJECT()),
        '$.handlerAction',
        JSON_OBJECT(
            'formSchema', JSON_ARRAY(
                JSON_OBJECT('key','processingResult','label','办理结果','type','textarea','required',true,'width','full','maxLength',1000,'placeholder','请填写实际办理结果')
            )
        )
    ),
    nodes = JSON_SET(
        nodes,
        CONCAT('$[', JSON_LENGTH(nodes) - 1, '].handlerAction'),
        JSON_OBJECT(
            'formSchema', JSON_ARRAY(
                JSON_OBJECT('key','processingResult','label','办理结果','type','textarea','required',true,'width','full','maxLength',1000,'placeholder','请填写实际办理结果')
            )
        )
    )
WHERE asset_type IN ('BUNDLE','PAGE','COMPUTER','MOBILE','STATIC_IP','EMAIL','ACCOUNT_OPERATION')
  AND deleted_at=0;
