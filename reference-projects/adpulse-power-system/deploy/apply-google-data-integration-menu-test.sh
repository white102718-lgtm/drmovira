#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
migration_file="${script_dir}/V27__add_google_data_integration_menu.sql"

if [[ ! -f "$migration_file" ]]; then
  echo "Google data integration menu migration not found: $migration_file" >&2
  exit 1
fi

docker exec -i adpulse-system-mysql sh -c \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  < "$migration_file"
echo DB_GOOGLE_DATA_INTEGRATION_MENU_APPLIED

docker exec adpulse-system-mysql sh -c \
  'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT child.menu_code, child.menu_name, child.route_path, child.component, child.permission_code, child.visible, child.sort_order, parent.menu_code AS parent_code FROM sys_menu child INNER JOIN sys_menu parent ON parent.id=child.parent_id AND parent.deleted_at=0 WHERE child.menu_code=\"SystemDataIntegration\" AND child.status=1 AND child.deleted_at=0; SELECT role.role_code, relation.menu_id FROM sys_role_menu relation INNER JOIN sys_role role ON role.id=relation.role_id AND role.deleted_at=0 INNER JOIN sys_menu menu ON menu.id=relation.menu_id AND menu.deleted_at=0 WHERE menu.menu_code=\"SystemDataIntegration\" AND relation.deleted_at=0 ORDER BY role.role_code;"' \
  2>/dev/null
