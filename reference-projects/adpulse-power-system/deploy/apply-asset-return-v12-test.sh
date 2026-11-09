#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
migration_file="${script_dir}/../adpulse-system/src/main/resources/db/migration/V12__create_asset_return_flow.sql"

if [[ ! -f "$migration_file" ]]; then
  echo "V12 migration not found: $migration_file" >&2
  exit 1
fi

# V12 中的建表、权限与角色授权均可安全重复执行，用于修复半迁移状态。
docker exec -i adpulse-system-mysql sh -c \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  < "$migration_file"
echo DB_V12_APPLIED

docker exec adpulse-system-mysql sh -c \
  'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) AS return_table_count FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=\"media_asset_return\"; SHOW COLUMNS FROM media_asset_return; SHOW INDEX FROM media_asset_return; SELECT menu_code, permission_code FROM sys_menu WHERE menu_code=\"MEDIA_RESOURCE_RETURN_MANAGE\" AND deleted_at=0"' \
  2>/dev/null
