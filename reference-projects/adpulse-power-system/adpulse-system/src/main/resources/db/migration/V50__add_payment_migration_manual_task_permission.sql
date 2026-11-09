SET @manual_task_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'SYSTEM_MANUAL_TASK'
      AND deleted_at = 0
    LIMIT 1
);

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, permission_code,
    status, sort_order, remark
)
SELECT @manual_task_id, 3, 'SYSTEM_MANUAL_TASK_PAYMENT_MIGRATION', '迁移旧系统打款申请',
       'system:manual-task:payment-migration', 1, 20,
       '允许预检并迁移旧系统已完成或已拒绝的打款申请'
WHERE @manual_task_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM sys_menu
      WHERE menu_code = 'SYSTEM_MANUAL_TASK_PAYMENT_MIGRATION'
        AND deleted_at = 0
  );

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, menu.id
FROM sys_role role
JOIN sys_menu menu
  ON menu.menu_code = 'SYSTEM_MANUAL_TASK_PAYMENT_MIGRATION'
 AND menu.deleted_at = 0
WHERE role.role_code = 'ADMIN'
  AND role.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1
      FROM sys_role_menu relation
      WHERE relation.role_id = role.id
        AND relation.menu_id = menu.id
        AND relation.deleted_at = 0
  );
