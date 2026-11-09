#!/usr/bin/env bash
set -euo pipefail

ssh -i /d/finalshell/pem/adpulse-power.pem \
  -o StrictHostKeyChecking=no \
  ubuntu@44.228.249.36 \
  "docker exec -i adpulse-system-mysql sh -lc 'exec mysql -N -u\"\$MYSQL_USER\" -p\"\$MYSQL_PASSWORD\" \"\$MYSQL_DATABASE\"'" <<'SQL'
SELECT CONCAT('CONFIG_COUNT|', COUNT(*))
FROM media_approval_config WHERE deleted_at=0;

SELECT CONCAT('CATEGORY_COUNT|', category, '|', COUNT(*))
FROM media_approval_config WHERE deleted_at=0 GROUP BY category ORDER BY category;

SELECT CONCAT('FIELD|', c.asset_type, '|', fields.position, '|', fields.field_key, '|',
              fields.field_label, '|', fields.field_type, '|', fields.is_required)
FROM media_approval_config c
JOIN JSON_TABLE(c.form_schema, '$[*]' COLUMNS(
  position FOR ORDINALITY,
  field_key VARCHAR(100) PATH '$.key',
  field_label VARCHAR(100) PATH '$.label',
  field_type VARCHAR(30) PATH '$.type',
  is_required VARCHAR(10) PATH '$.required'
)) fields
WHERE c.deleted_at=0
ORDER BY c.id, fields.position;

SELECT CONCAT('FLOW|', asset_type, '|NODES=', JSON_LENGTH(nodes),
              '|FIRST_APPROVER=', JSON_UNQUOTE(JSON_EXTRACT(nodes, '$[0].approverName')),
              '|FIRST_HANDLER=', JSON_UNQUOTE(JSON_EXTRACT(nodes, '$[0].handlerName')),
              '|SAME=', JSON_UNQUOTE(JSON_EXTRACT(nodes, '$[0].handlerIsApprover')))
FROM media_approval_config WHERE deleted_at=0 ORDER BY id;

SELECT CONCAT('RECOMMEND|', c.asset_type, '|', COUNT(a.id))
FROM media_approval_config c
JOIN sys_user u ON u.phone='15666666666' AND u.deleted_at=0
LEFT JOIN media_asset_application a ON a.asset_type=c.asset_type
  AND a.requester_id=u.id AND a.deleted_at=0
WHERE c.deleted_at=0 AND c.enabled=1
GROUP BY c.id, c.asset_type, c.flow_name
ORDER BY COUNT(a.id) DESC, c.flow_name LIMIT 3;

START TRANSACTION;
INSERT INTO media_approval_config
  (asset_type, category, flow_name, approver_id, approver_name, cc_user_ids,
   form_schema, nodes, enabled, created_by, updated_by)
SELECT 'CUSTOM_VERIFY', 'finance', '付款申请验证', approver_id, approver_name, '',
       JSON_ARRAY(JSON_OBJECT('key','amount','label','金额','type','number','required',true)),
       nodes, 1, created_by, updated_by
FROM media_approval_config WHERE asset_type='PERSONAL' AND deleted_at=0 LIMIT 1;
SELECT CONCAT('CUSTOM_CONFIG|', asset_type, '|', category, '|', flow_name, '|', JSON_LENGTH(form_schema))
FROM media_approval_config WHERE asset_type='CUSTOM_VERIFY';
ROLLBACK;
SELECT CONCAT('CUSTOM_ROLLBACK|', COUNT(*)) FROM media_approval_config WHERE asset_type='CUSTOM_VERIFY';
SQL
