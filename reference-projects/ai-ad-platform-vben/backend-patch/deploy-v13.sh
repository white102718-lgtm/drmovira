#!/usr/bin/env bash
set -euo pipefail

KEY=/d/finalshell/pem/adpulse-power.pem
HOST=ubuntu@44.228.249.36
REMOTE_DIR=/home/ubuntu/adpulse-v13
MIGRATION=V13__project_closure_application_fields.sql

ssh -i "$KEY" -o StrictHostKeyChecking=no "$HOST" "mkdir -p '$REMOTE_DIR'"
scp -i "$KEY" -o StrictHostKeyChecking=no \
  "backend-patch/db/migration/$MIGRATION" "$HOST:$REMOTE_DIR/$MIGRATION"

ssh -i "$KEY" -o StrictHostKeyChecking=no "$HOST" <<'REMOTE'
set -euo pipefail
APP=/opt/docker/java/system
REMOTE_DIR=/home/ubuntu/adpulse-v13
RELEASE="$(date +%Y%m%d%H%M%S)"
BACKUP="$APP/backups/adpulse-project-closure-form-$RELEASE.sql"

docker exec adpulse-system-mysql sh -lc \
  'exec mysqldump --no-tablespaces -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" media_approval_config' \
  > "$BACKUP"
test -s "$BACKUP"

docker exec -i adpulse-system-mysql sh -lc \
  'exec mysql --default-character-set=utf8mb4 -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
  < "$REMOTE_DIR/V13__project_closure_application_fields.sql"

docker exec adpulse-system-mysql sh -lc \
  'exec mysql -N --default-character-set=utf8mb4 -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' <<'SQL'
SELECT CONCAT('CONFIG|', asset_type, '|', JSON_LENGTH(form_schema), '|', enabled)
FROM media_approval_config
WHERE asset_type = 'PROJECT_CLOSURE' AND deleted_at = 0;
SQL

echo "DB_RELEASE=$RELEASE"
echo "DB_BACKUP=$BACKUP"
REMOTE
