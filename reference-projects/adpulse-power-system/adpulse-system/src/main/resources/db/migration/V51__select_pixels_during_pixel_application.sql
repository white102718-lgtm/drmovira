-- 按稳定业务名称升级启用的“像素申请”，避免误改同样使用 PIXEL 标识的“像素批量申请”。
-- 历史申请使用提交时的表单和节点快照，不在本迁移中修改。
UPDATE media_approval_config config
JOIN media_application_definition definition
  ON definition.approval_config_id = config.id
 AND definition.deleted_at = 0
 AND definition.status = 1
SET config.description = '申请人选择所属项目、使用团队和具体像素；最终审批通过后自动完成项目分配。',
    config.settings = JSON_SET(
        JSON_REMOVE(
            COALESCE(config.settings, JSON_OBJECT()),
            '$.handlerAction',
            '$.handlerSource',
            '$.handlerApprovalNodeId'
        ),
        '$.approvalType', 'manual',
        '$.completionMode', 'pixel-auto-assign'
    ),
    config.form_schema = JSON_ARRAY(
        JSON_OBJECT(
            'key', 'projectId',
            'label', '所属项目',
            'type', 'select',
            'required', true,
            'width', 'half',
            'optionSource', 'projects',
            'placeholder', '请选择项目'
        ),
        JSON_OBJECT(
            'key', 'usageTeamId',
            'label', '使用团队',
            'type', 'select',
            'required', true,
            'width', 'half',
            'optionSource', 'departments',
            'placeholder', '请选择使用团队'
        ),
        JSON_OBJECT(
            'key', 'pixelAssetIds',
            'label', '选择像素',
            'type', 'pixel-selector',
            'required', true,
            'width', 'full',
            'optionSource', 'available-pixels',
            'placeholder', '打开弹窗选择未分配像素',
            'helpText', '支持按像素 ID、名称及其他像素信息批量筛选'
        )
    ),
    config.updated_at = CURRENT_TIMESTAMP(3)
WHERE config.deleted_at = 0
  AND config.enabled = 1
  AND definition.application_name = '像素申请';

UPDATE media_application_definition
SET description = '选择项目、使用团队和具体像素；最终审批通过后自动完成分配。',
    updated_at = CURRENT_TIMESTAMP(3)
WHERE deleted_at = 0
  AND status = 1
  AND application_name = '像素申请';
