-- Project closure approval configuration and application catalog.
SET NAMES utf8mb4;
START TRANSACTION;

SET @group_name = CONVERT(0xE4B89AE58AA1E4B88EE9A1B9E79BAE USING utf8mb4);
SET @flow_name = CONVERT(0xE9A1B9E79BAEE7BB93E9A1B9E5AEA1E689B9 USING utf8mb4);
SET @flow_description = CONVERT(0xE58F91E8B5B7E9A1B9E79BAEE7BB93E9A1B9E5AEA1E689B9EFBC8CE5B9B6E59CA8E794B3E8AFB7E58D95E4B8ADE98089E68BA9E99C80E8A681E7BB93E9A1B9E79A84E9A1B9E79BAEE38082 USING utf8mb4);
SET @fallback_operator_name = CONVERT(0xE7B3BBE7BB9FE7AEA1E79086E59198 USING utf8mb4);
SET @section_label = CONVERT(0xE7BB93E9A1B9E9A1B9E79BAEE4BFA1E681AF USING utf8mb4);
SET @project_label = CONVERT(0xE9A1B9E79BAE USING utf8mb4);
SET @project_placeholder = CONVERT(0xE8AFB7E98089E68BA9E99C80E8A681E7BB93E9A1B9E79A84E9A1B9E79BAE USING utf8mb4);
SET @approver_node_name = CONVERT(0xE4B89AE58AA1E8B49FE8B4A3E4BABAE5AEA1E689B9 USING utf8mb4);
SET @application_description = CONVERT(0xE98089E68BA9E9A1B9E79BAEE5B9B6E58F91E8B5B7E7BB93E9A1B9E5AEA1E689B9E38082 USING utf8mb4);

SET @operator_id = (
  SELECT id
  FROM sys_user
  WHERE status = 1 AND deleted_at = 0
  ORDER BY id
  LIMIT 1
);

INSERT INTO media_approval_group (
  group_name, sort_order, created_by, updated_by, created_at, updated_at, deleted_at
)
SELECT @group_name, 30, @operator_id, @operator_id,
       CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3), 0
WHERE @operator_id IS NOT NULL
ON DUPLICATE KEY UPDATE
  sort_order = VALUES(sort_order),
  updated_by = VALUES(updated_by),
  updated_at = VALUES(updated_at),
  deleted_at = 0;

SET @project_group_id = (
  SELECT id
  FROM media_approval_group
  WHERE group_name = @group_name AND deleted_at = 0
  ORDER BY id
  LIMIT 1
);

INSERT INTO media_approval_config (
  asset_type, category, flow_name, description, group_id, group_name, icon,
  visibility, settings, sort_order, approver_id, approver_name, cc_user_ids,
  form_schema, nodes, enabled, created_by, updated_by, created_at, updated_at, deleted_at
)
SELECT
  'PROJECT_CLOSURE', 'advertising', @flow_name, @flow_description,
  @project_group_id, @group_name, 'lucide:circle-check-big', 'all',
  JSON_OBJECT('approvalType', 'manual'), 130,
  @operator_id, COALESCE(u.display_name, @fallback_operator_name), '',
  JSON_ARRAY(
    JSON_OBJECT('key', 'sectionProject', 'label', @section_label,
                'type', 'section', 'required', false, 'width', 'full'),
    JSON_OBJECT('key', 'projectId', 'label', @project_label, 'type', 'select',
                'required', true, 'width', 'half', 'optionSource', 'projects',
                'placeholder', @project_placeholder)
  ),
  JSON_ARRAY(
    JSON_OBJECT('name', @approver_node_name, 'approverId', CAST(@operator_id AS CHAR),
                'approverName', COALESCE(u.display_name, @fallback_operator_name))
  ),
  1, @operator_id, @operator_id, CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3), 0
FROM sys_user u
WHERE u.id = @operator_id
ON DUPLICATE KEY UPDATE
  category = VALUES(category),
  flow_name = VALUES(flow_name),
  description = VALUES(description),
  group_id = VALUES(group_id),
  group_name = VALUES(group_name),
  icon = VALUES(icon),
  visibility = VALUES(visibility),
  settings = VALUES(settings),
  sort_order = VALUES(sort_order),
  approver_id = VALUES(approver_id),
  approver_name = VALUES(approver_name),
  form_schema = VALUES(form_schema),
  nodes = VALUES(nodes),
  enabled = VALUES(enabled),
  updated_by = VALUES(updated_by),
  updated_at = VALUES(updated_at),
  deleted_at = 0;

SET @project_closure_config_id = (
  SELECT id
  FROM media_approval_config
  WHERE asset_type = 'PROJECT_CLOSURE' AND deleted_at = 0
  ORDER BY id
  LIMIT 1
);

INSERT INTO media_application_definition (
  application_code, application_name, category, description, icon, approval_config_id,
  operation_type, visibility, sort_order, status, created_by, updated_by,
  created_at, updated_at, deleted_at
)
SELECT
  'PROJECT_CLOSURE', @flow_name, 'advertising',
  @application_description, 'lucide:circle-check-big', @project_closure_config_id,
  NULL, 'all', 130, 1, @operator_id, @operator_id,
  CURRENT_TIMESTAMP(3), CURRENT_TIMESTAMP(3), 0
WHERE @operator_id IS NOT NULL
  AND @project_closure_config_id IS NOT NULL
ON DUPLICATE KEY UPDATE
  application_name = VALUES(application_name),
  category = VALUES(category),
  description = VALUES(description),
  icon = VALUES(icon),
  approval_config_id = VALUES(approval_config_id),
  visibility = VALUES(visibility),
  sort_order = VALUES(sort_order),
  status = VALUES(status),
  updated_by = VALUES(updated_by),
  updated_at = VALUES(updated_at),
  deleted_at = 0;

COMMIT;
