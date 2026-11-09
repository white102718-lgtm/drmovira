#!/usr/bin/env bash
set -Eeuo pipefail

column_count="$(docker exec adpulse-system-mysql sh -c \
  'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=\"media_asset\" AND column_name=\"project_id\""' \
  2>/dev/null)"

if [[ "$column_count" == "0" ]]; then
  docker exec -i adpulse-system-mysql sh -c \
    'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
    < /tmp/V8__scope_media_assets_by_project.sql
  echo DB_V8_APPLIED
else
  echo DB_V8_ALREADY_PRESENT
fi

docker exec adpulse-system-mysql sh -c \
  'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SHOW COLUMNS FROM media_asset LIKE \"project_%\"; SHOW INDEX FROM media_asset WHERE Key_name=\"idx_media_asset_project\""' \
  2>/dev/null
