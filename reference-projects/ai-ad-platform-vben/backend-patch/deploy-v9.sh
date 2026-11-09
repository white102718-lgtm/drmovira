#!/usr/bin/env bash
set -euo pipefail

KEY=/d/finalshell/pem/adpulse-power.pem
HOST=ubuntu@44.228.249.36
REMOTE_DIR=/home/ubuntu/adpulse-v9
MIGRATION=V9__approval_config_application_catalog.sql

ssh -i "$KEY" -o StrictHostKeyChecking=no "$HOST" "mkdir -p '$REMOTE_DIR'"
scp -i "$KEY" -o StrictHostKeyChecking=no \
  "backend-patch/db/migration/$MIGRATION" "$HOST:$REMOTE_DIR/$MIGRATION"

ssh -i "$KEY" -o StrictHostKeyChecking=no "$HOST" <<'REMOTE'
set -euo pipefail
APP=/opt/docker/java/system
REMOTE_DIR=/home/ubuntu/adpulse-v9
RELEASE="$(date +%Y%m%d%H%M%S)"
BACKUP="$APP/backups/adpulse-approval-catalog-$RELEASE.sql"

docker exec adpulse-system-mysql sh -lc \
  'exec mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" media_approval_config media_asset_application media_asset_approval_log system_notification' \
  > "$BACKUP"
test -s "$BACKUP"

docker exec -i adpulse-system-mysql sh -lc \
  'exec mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
  < "$REMOTE_DIR/V9__approval_config_application_catalog.sql"

docker exec -i adpulse-system-mysql sh -lc \
  'exec mysql -N -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' <<'SQL'
SELECT CONCAT('CATEGORY_COLUMN|', COUNT(*))
FROM information_schema.columns
WHERE table_schema=DATABASE() AND table_name='media_approval_config' AND column_name='category';
SELECT CONCAT('CONFIG|', asset_type, '|', category, '|', flow_name, '|', JSON_LENGTH(form_schema), '|', JSON_LENGTH(nodes), '|', enabled)
FROM media_approval_config WHERE deleted_at=0 ORDER BY id;
SQL

echo "DB_RELEASE=$RELEASE"
echo "DB_BACKUP=$BACKUP"
REMOTE
