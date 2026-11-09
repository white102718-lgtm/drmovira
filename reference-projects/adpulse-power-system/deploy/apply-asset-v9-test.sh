#!/usr/bin/env bash
set -Eeuo pipefail

column_count="$(docker exec adpulse-system-mysql sh -c \
  'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=\"media_asset\" AND column_name=\"channel_id\""' \
  2>/dev/null)"

if [[ "$column_count" == "0" ]]; then
  docker exec -i adpulse-system-mysql sh -c \
    'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
    < /tmp/V9__add_asset_channel_snapshot.sql
  echo DB_V9_APPLIED
else
  echo DB_V9_ALREADY_PRESENT
fi

docker exec adpulse-system-mysql sh -c \
  'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SHOW COLUMNS FROM media_asset LIKE \"channel_%\"; SHOW INDEX FROM media_asset WHERE Key_name=\"idx_media_asset_channel\""' \
  2>/dev/null
