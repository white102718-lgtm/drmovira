#!/usr/bin/env bash
set -euo pipefail

KEY=/d/finalshell/pem/adpulse-power.pem
HOST=ubuntu@44.228.249.36
REMOTE_DIR=/home/ubuntu/adpulse-v11
MIGRATION=V11__mpower_form_constraints.sql

ssh -i "$KEY" -o StrictHostKeyChecking=no "$HOST" "mkdir -p '$REMOTE_DIR'"
scp -i "$KEY" -o StrictHostKeyChecking=no \
  "backend-patch/db/migration/$MIGRATION" "$HOST:$REMOTE_DIR/$MIGRATION"

ssh -i "$KEY" -o StrictHostKeyChecking=no "$HOST" <<'REMOTE'
set -euo pipefail
APP=/opt/docker/java/system
REMOTE_DIR=/home/ubuntu/adpulse-v11
RELEASE="$(date +%Y%m%d%H%M%S)"
BACKUP="$APP/backups/adpulse-form-constraints-$RELEASE.sql"

docker exec adpulse-system-mysql sh -lc \
  'exec mysqldump --no-tablespaces -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" media_approval_config' \
  > "$BACKUP"
test -s "$BACKUP"

docker exec -i adpulse-system-mysql sh -lc \
  'exec mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
  < "$REMOTE_DIR/V11__mpower_form_constraints.sql"

docker exec -i adpulse-system-mysql sh -lc \
  'exec mysql -N -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' <<'SQL'
SELECT CONCAT('FIELD|', c.asset_type, '|', fields.position, '|', fields.field_label,
              '|MAX=', COALESCE(fields.max_length, 'none'),
              '|RULE=', COALESCE(fields.validation_rule, 'none'))
FROM media_approval_config c
JOIN JSON_TABLE(c.form_schema, '$[*]' COLUMNS(
  position FOR ORDINALITY,
  field_label VARCHAR(100) PATH '$.label',
  max_length VARCHAR(20) PATH '$.maxLength' NULL ON EMPTY,
  validation_rule VARCHAR(30) PATH '$.validationRule' NULL ON EMPTY
)) fields
WHERE c.asset_type IN ('PERSONAL', 'BM', 'PIXEL', 'TG') AND c.deleted_at=0
ORDER BY c.id, fields.position;
SQL

echo "DB_RELEASE=$RELEASE"
echo "DB_BACKUP=$BACKUP"
REMOTE
