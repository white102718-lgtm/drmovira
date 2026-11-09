-- 像素申请办理仅记录办理结果，不再从库存选择或分配像素资产。
UPDATE media_approval_config
SET settings = JSON_SET(
        COALESCE(settings, JSON_OBJECT()),
        '$.handlerAction.resourceAssignment',
        JSON_OBJECT('enabled', false)
    ),
    nodes = CASE
        WHEN JSON_LENGTH(nodes) > 0 THEN JSON_SET(
            nodes,
            CONCAT('$[', JSON_LENGTH(nodes) - 1, '].handlerAction.resourceAssignment'),
            JSON_OBJECT('enabled', false)
        )
        ELSE nodes
    END
WHERE asset_type = 'PIXEL'
  AND deleted_at = 0;
