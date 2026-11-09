-- Fixed daily-report applications. Field entry is implemented in the frontend
-- business form; this catalog only controls routing, approvers and visibility.
SET NAMES utf8mb4;

-- The historical asset-type column is only 24 characters wide. Both daily-report
-- codes must be stored in full so that approval records can be routed reliably.
ALTER TABLE media_approval_config
  MODIFY COLUMN asset_type VARCHAR(64) NOT NULL;

START TRANSACTION;

SET @operator_id = (
  SELECT id FROM sys_user
  WHERE status = 1 AND deleted_at = 0
  ORDER BY id LIMIT 1
);
SET @operator_name = (
  SELECT display_name FROM sys_user
  WHERE id = @operator_id
);

INSERT INTO media_approval_group (
  group_name, sort_order, created_by, updated_by, created_at, updated_at, deleted_at
)
SELECT '业务与项目', 30, @operator_id, @operator_id,
       CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3), 0
WHERE @operator_id IS NOT NULL
ON DUPLICATE KEY UPDATE updated_by = VALUES(updated_by), updated_at = VALUES(updated_at), deleted_at = 0;

SET @group_id = (
  SELECT id FROM media_approval_group
  WHERE group_name = '业务与项目' AND deleted_at = 0
  ORDER BY id LIMIT 1
);

INSERT INTO media_approval_config (
  asset_type, category, flow_name, description, group_id, group_name, icon,
  visibility, settings, sort_order, approver_id, approver_name, cc_user_ids,
  form_schema, nodes, enabled, created_by, updated_by, created_at, updated_at, deleted_at
)
SELECT seed.asset_type, 'advertising', seed.flow_name, seed.description,
       @group_id, '业务与项目', seed.icon, 'all',
       JSON_OBJECT('approvalType', 'manual', 'fixedBusinessForm', true),
       seed.sort_order, @operator_id, COALESCE(@operator_name, '系统管理员'), '',
       -- This is a detail snapshot hint only. The executable form is the fixed frontend page.
       JSON_ARRAY(JSON_OBJECT('key', 'fixedForm', 'label', '固定业务表单',
                              'type', 'textarea', 'required', false, 'width', 'full',
                              'readOnly', true)),
       JSON_ARRAY(JSON_OBJECT('name', '业务负责人审批',
                              'approverId', CAST(@operator_id AS CHAR),
                              'approverName', COALESCE(@operator_name, '系统管理员'))),
       1, @operator_id, @operator_id, CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3), 0
FROM (
  SELECT 'DELIVERY_DAILY_REPORT' AS asset_type, '投放日报申请' AS flow_name,
         '按任务线批量填写投放日报并提交审批。' AS description,
         'lucide:chart-no-axes-combined' AS icon, 140 AS sort_order
  UNION ALL
  SELECT 'MATERIAL_DESIGNER_DAILY_REPORT', '素材师日报申请',
         '提交素材师结算日报并关联投放师、项目和任务线。',
         'lucide:badge-percent', 150
) seed
WHERE @operator_id IS NOT NULL
ON DUPLICATE KEY UPDATE
  category = VALUES(category), flow_name = VALUES(flow_name), description = VALUES(description),
  group_id = VALUES(group_id), group_name = VALUES(group_name), icon = VALUES(icon),
  visibility = VALUES(visibility), settings = VALUES(settings), sort_order = VALUES(sort_order),
  approver_id = VALUES(approver_id), approver_name = VALUES(approver_name), nodes = VALUES(nodes),
  enabled = VALUES(enabled), updated_by = VALUES(updated_by), updated_at = VALUES(updated_at), deleted_at = 0;

INSERT INTO media_application_definition (
  application_code, application_name, category, description, icon, approval_config_id,
  operation_type, visibility, sort_order, status, created_by, updated_by,
  created_at, updated_at, deleted_at
)
SELECT seed.application_code, seed.application_name, 'advertising', seed.description, seed.icon,
       config.id, NULL, 'all', seed.sort_order, 1, @operator_id, @operator_id,
       CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3), 0
FROM (
  SELECT 'DELIVERY_DAILY_REPORT' AS application_code, '投放日报申请' AS application_name,
         '按任务线批量填写投放日报并提交审批。' AS description,
         'lucide:chart-no-axes-combined' AS icon, 140 AS sort_order
  UNION ALL
  SELECT 'MATERIAL_DESIGNER_DAILY_REPORT', '素材师日报申请',
         '提交素材师结算日报并关联投放师、项目和任务线。',
         'lucide:badge-percent', 150
) seed
JOIN media_approval_config config
  ON config.asset_type = seed.application_code AND config.deleted_at = 0
WHERE @operator_id IS NOT NULL
ON DUPLICATE KEY UPDATE
  application_name = VALUES(application_name), category = VALUES(category),
  description = VALUES(description), icon = VALUES(icon),
  approval_config_id = VALUES(approval_config_id), visibility = VALUES(visibility),
  sort_order = VALUES(sort_order), status = VALUES(status), updated_by = VALUES(updated_by),
  updated_at = VALUES(updated_at), deleted_at = 0;

COMMIT;
