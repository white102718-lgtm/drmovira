-- 已部署的像素申请配置补充显式团队选择；部门 ID 用于稳定关联，名称快照用于审批展示和资产分配。
ALTER TABLE media_asset
    MODIFY COLUMN usage_team VARCHAR(128) NULL
        COMMENT '像素申请选择的使用团队名称快照；项目结项释放时清空';

UPDATE media_approval_config
SET description = '选择所属项目、使用团队和像素数量；审批通过后由办理人从未分配像素库存中选择对应数量。',
    form_schema = JSON_ARRAY_INSERT(
        form_schema,
        '$[1]',
        JSON_OBJECT(
            'key', 'usageTeamId',
            'label', '使用团队',
            'type', 'select',
            'required', true,
            'width', 'half',
            'optionSource', 'departments',
            'placeholder', '请选择使用团队'
        )
    )
WHERE asset_type = 'PIXEL'
  AND enabled = 1
  AND deleted_at = 0
  AND JSON_SEARCH(form_schema, 'one', 'usageTeamId', NULL, '$[*].key') IS NULL;

UPDATE media_application_definition
SET description = '按项目与使用团队申请像素库存，由审批办理环节完成分配。'
WHERE application_code = 'PIXEL'
  AND status = 1
  AND deleted_at = 0;
