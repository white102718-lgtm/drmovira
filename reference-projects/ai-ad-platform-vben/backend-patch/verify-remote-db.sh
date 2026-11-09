#!/usr/bin/env bash
set -euo pipefail

ssh -i /d/finalshell/pem/adpulse-power.pem \
  -o StrictHostKeyChecking=no \
  ubuntu@44.228.249.36 \
  "docker exec -i adpulse-system-mysql sh -lc 'exec mysql -N -u\"\$MYSQL_USER\" -p\"\$MYSQL_PASSWORD\" \"\$MYSQL_DATABASE\"'" <<'SQL'
SELECT CONCAT('CONFIG|', asset_type, '|', flow_name, '|', JSON_LENGTH(form_schema), '|', JSON_LENGTH(nodes), '|', enabled)
FROM media_approval_config WHERE deleted_at=0 ORDER BY asset_type;
SELECT CONCAT('NOTIFICATION_TABLE|', COUNT(*))
FROM information_schema.tables
WHERE table_schema=DATABASE() AND table_name='system_notification';
SELECT CONCAT('COLUMN|', table_name, '|', column_name)
FROM information_schema.columns
WHERE table_schema=DATABASE()
  AND ((table_name='media_approval_config' AND column_name IN ('flow_name','form_schema','nodes','enabled'))
    OR (table_name='media_asset_application' AND column_name IN ('form_data','form_schema_snapshot','nodes_snapshot','current_node_index'))
    OR (table_name='media_asset_approval_log' AND column_name IN ('node_index','node_name')))
ORDER BY table_name, column_name;
SQL
