#!/usr/bin/env bash
set -Eeuo pipefail

table_count="$(docker exec adpulse-system-mysql sh -c \
  'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=\"media_asset_application_comment\""' \
  2>/dev/null)"

if [[ "$table_count" == "0" ]]; then
  docker exec -i adpulse-system-mysql sh -c \
    'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
    < /tmp/V21__create_asset_application_comments.sql
  echo DB_V21_APPLIED
else
  echo DB_V21_ALREADY_PRESENT
fi

docker exec adpulse-system-mysql sh -c \
  'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SHOW CREATE TABLE media_asset_application_comment"' \
  2>/dev/null
