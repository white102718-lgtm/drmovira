-- 重建像素申请入口与审批配置：表单只保留项目和像素数量，办理节点从未分配像素库存中选择。
SET @pixel_operator_id = COALESCE(
    (SELECT approver_id FROM media_approval_config
      WHERE asset_type = 'PIXEL' AND deleted_at = 0 ORDER BY id DESC LIMIT 1),
    (SELECT id FROM sys_user WHERE status = 1 AND deleted_at = 0 ORDER BY id LIMIT 1),
    (SELECT id FROM sys_user WHERE deleted_at = 0 ORDER BY id LIMIT 1),
    0
);
SET @pixel_operator_name = COALESCE(
    (SELECT COALESCE(NULLIF(display_name, ''), NULLIF(real_name, ''), username)
       FROM sys_user WHERE id = @pixel_operator_id AND deleted_at = 0),
    '系统管理员'
);
SET @advertising_application_type_id = (
    SELECT id FROM media_application_type
     WHERE type_name = '广告资产' AND deleted_at = 0 ORDER BY id LIMIT 1
);

-- 旧入口和审批配置只做软删除，历史申请保持其提交时的表单和流程快照。
UPDATE media_application_definition
SET status = 0,
    deleted_at = CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED) + id,
    updated_by = @pixel_operator_id
WHERE (application_code = 'PIXEL' OR application_name = '像素申请')
  AND deleted_at = 0;

UPDATE media_approval_config
SET enabled = 0,
    deleted_at = CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED) + id,
    updated_by = @pixel_operator_id
WHERE (asset_type = 'PIXEL' OR flow_name = '像素申请')
  AND deleted_at = 0;

INSERT INTO media_approval_config (
    asset_type, category, approver_id, approver_name, cc_user_ids, flow_name,
    description, icon, visibility, settings, sort_order, form_schema, nodes,
    enabled, created_by, updated_by
) VALUES (
    'PIXEL', 'advertising', @pixel_operator_id, @pixel_operator_name, '', '像素申请',
    '申请项目所需的像素数量；审批通过后由办理人从未分配像素库存中选择对应数量。',
    'lucide:scan-line', 'all',
    JSON_OBJECT('approvalType', 'manual', 'handlerAction', JSON_OBJECT(
        'resourceAssignment', JSON_OBJECT(
            'enabled', true,
            'assetTypeSource', 'application',
            'quantityFieldKey', 'quantity',
            'channelFieldKey', ''
        )
    )),
    30,
    JSON_ARRAY(
        JSON_OBJECT('key', 'projectId', 'label', '所属项目', 'type', 'select', 'required', true,
            'width', 'half', 'optionSource', 'projects', 'placeholder', '请选择项目'),
        JSON_OBJECT('key', 'quantity', 'label', '像素数量', 'type', 'number', 'required', true,
            'width', 'half', 'minValue', 1, 'placeholder', '请输入像素数量')
    ),
    JSON_ARRAY(
        JSON_OBJECT('id', 'PIXEL-approval', 'kind', 'approval', 'name', '业务负责人审批',
            'assigneeMode', 'member', 'approverType', 'USERS',
            'approverId', CAST(@pixel_operator_id AS CHAR), 'approverName', @pixel_operator_name,
            'approverIds', JSON_ARRAY(CAST(@pixel_operator_id AS CHAR)),
            'approverNames', JSON_ARRAY(@pixel_operator_name),
            'handlerId', CAST(@pixel_operator_id AS CHAR), 'handlerName', @pixel_operator_name,
            'handlerAction', JSON_OBJECT('resourceAssignment', JSON_OBJECT(
                'enabled', true,
                'assetTypeSource', 'application',
                'quantityFieldKey', 'quantity',
                'channelFieldKey', ''
            )))
    ),
    1, @pixel_operator_id, @pixel_operator_id
);

SET @pixel_config_id = LAST_INSERT_ID();

INSERT INTO media_application_definition (
    application_code, application_name, application_type_id, description, icon,
    approval_config_id, visibility, show_in_resource_application, sort_order,
    status, created_by, updated_by
) VALUES (
    'PIXEL', '像素申请', @advertising_application_type_id,
    '按项目申请像素库存，由审批办理环节完成分配。', 'lucide:scan-line',
    @pixel_config_id, 'all', 1, 30, 1, @pixel_operator_id, @pixel_operator_id
);
