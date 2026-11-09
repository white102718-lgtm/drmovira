#!/usr/bin/env bash
set -euo pipefail

KEY=/d/finalshell/pem/adpulse-power.pem
HOST=ubuntu@44.228.249.36
REMOTE_DIR=/home/ubuntu/adpulse-v12
MIGRATION=V12__project_closure_approval.sql

ssh -i "$KEY" -o StrictHostKeyChecking=no "$HOST" "mkdir -p '$REMOTE_DIR'"
scp -i "$KEY" -o StrictHostKeyChecking=no \
  "backend-patch/db/migration/$MIGRATION" "$HOST:$REMOTE_DIR/$MIGRATION"

ssh -i "$KEY" -o StrictHostKeyChecking=no "$HOST" <<'REMOTE'
set -euo pipefail
APP=/opt/docker/java/system
REMOTE_DIR=/home/ubuntu/adpulse-v12
RELEASE="$(date +%Y%m%d%H%M%S)"
BACKUP="$APP/backups/adpulse-project-closure-$RELEASE.sql"

docker exec adpulse-system-mysql sh -lc \
  'exec mysqldump --no-tablespaces -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" media_approval_group media_approval_config media_application_definition' \
  > "$BACKUP"
test -s "$BACKUP"

docker exec -i adpulse-system-mysql sh -lc \
  'exec mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
  < "$REMOTE_DIR/V12__project_closure_approval.sql"

docker exec adpulse-system-mysql sh -lc \
  'exec mysql -N -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' <<'SQL'
SELECT CONCAT('CONFIG|', id, '|', asset_type, '|', flow_name, '|', enabled)
FROM media_approval_config
WHERE asset_type = 'PROJECT_CLOSURE' AND deleted_at = 0;

SELECT CONCAT('APPLICATION|', id, '|', application_code, '|', approval_config_id, '|', status)
FROM media_application_definition
WHERE application_code = 'PROJECT_CLOSURE' AND deleted_at = 0;
SQL

echo "DB_RELEASE=$RELEASE"
echo "DB_BACKUP=$BACKUP"
REMOTE
