#!/usr/bin/env bash
set -Eeuo pipefail

count="$(docker exec adpulse-system-mysql sh -c \
  'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=\"media_asset\""' \
  2>/dev/null)"

if [[ "$count" == "0" ]]; then
  docker exec -i adpulse-system-mysql sh -c \
    'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
    < /tmp/V7__create_asset_approval_flow.sql
  echo DB_V7_APPLIED
else
  echo DB_V7_ALREADY_PRESENT
fi

docker exec adpulse-system-mysql sh -c \
  'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SHOW TABLES LIKE \"media_asset%\"; SHOW TABLES LIKE \"media_approval_config\""' \
  2>/dev/null
