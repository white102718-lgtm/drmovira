-- 九类资源均需在办理节点选择库存并分配；绑包、打款和账户操作仍只记录办理结果。
-- PAGE 的申请数量字段沿用 MPower 的 pageCount，其余库存类型使用 quantity。
UPDATE media_approval_config
SET settings = JSON_SET(
        COALESCE(settings, JSON_OBJECT()),
        '$.handlerAction',
        JSON_OBJECT(
            'resourceAssignment', JSON_OBJECT(
                'assetTypeSource', 'application',
                'channelFieldKey',
                    CASE
                        WHEN asset_type IN ('PERSONAL', 'BM', 'PIXEL', 'TG') THEN 'channelId'
                        ELSE ''
                    END,
                'enabled', TRUE,
                'quantityFieldKey',
                    CASE WHEN asset_type = 'PAGE' THEN 'pageCount' ELSE 'quantity' END
            )
        )
    ),
    nodes = JSON_SET(
        nodes,
        CONCAT('$[', JSON_LENGTH(nodes) - 1, '].handlerAction'),
        JSON_OBJECT(
            'resourceAssignment', JSON_OBJECT(
                'assetTypeSource', 'application',
                'channelFieldKey',
                    CASE
                        WHEN asset_type IN ('PERSONAL', 'BM', 'PIXEL', 'TG') THEN 'channelId'
                        ELSE ''
                    END,
                'enabled', TRUE,
                'quantityFieldKey',
                    CASE WHEN asset_type = 'PAGE' THEN 'pageCount' ELSE 'quantity' END
            )
        )
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE asset_type IN (
        'PERSONAL', 'BM', 'PIXEL', 'TG', 'PAGE',
        'COMPUTER', 'MOBILE', 'STATIC_IP', 'EMAIL'
    )
  AND deleted_at = 0
  AND JSON_LENGTH(nodes) > 0;

-- 已进入审批/办理的存量申请使用节点快照，必须同步补齐，避免发布后仍按旧办理表单执行。
UPDATE media_asset_application
SET nodes_snapshot = JSON_SET(
        nodes_snapshot,
        CONCAT('$[', JSON_LENGTH(nodes_snapshot) - 1, '].handlerAction'),
        JSON_OBJECT(
            'resourceAssignment', JSON_OBJECT(
                'assetTypeSource', 'application',
                'channelFieldKey',
                    CASE
                        WHEN asset_type IN ('PERSONAL', 'BM', 'PIXEL', 'TG') THEN 'channelId'
                        ELSE ''
                    END,
                'enabled', TRUE,
                'quantityFieldKey',
                    CASE WHEN asset_type = 'PAGE' THEN 'pageCount' ELSE 'quantity' END
            )
        )
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE asset_type IN (
        'PERSONAL', 'BM', 'PIXEL', 'TG', 'PAGE',
        'COMPUTER', 'MOBILE', 'STATIC_IP', 'EMAIL'
    )
  AND status IN ('PENDING', 'PROCESSING')
  AND deleted_at = 0
  AND JSON_LENGTH(nodes_snapshot) > 0;
