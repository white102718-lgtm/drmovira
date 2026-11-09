-- 物理删除飞书组织同步产生的部门和用户，用于修正错误同步后重新全量同步。
--
-- 适用前提：这些飞书用户和部门刚刚同步完成，尚未参与业务单据或审批流程。
-- 安全规则：
-- 1. 仅处理 source_type = 'FEISHU' 的记录，不处理手工创建的 LOCAL 数据。
-- 2. 默认 confirm 开关为 0；确认预检结果后改为 1，再执行整份脚本。
-- 3. 若有效手工用户或手工部门仍引用目标飞书部门，脚本不会执行任何修改。
-- 4. 同步日志、登录日志和操作日志作为历史审计数据保留。
-- 5. SQL 无法撤销 Redis 会话；执行后必须通过应用或受控运维脚本撤销目标用户的
--    adpulse:session:* 会话。

SET @confirm_feishu_physical_delete = 0;

-- NULL 表示删除全部飞书租户；如只清理一个租户，请填写对应 tenant_key。
SET @feishu_tenant_key = NULL;

DROP TEMPORARY TABLE IF EXISTS tmp_feishu_delete_users;
DROP TEMPORARY TABLE IF EXISTS tmp_feishu_delete_departments;

CREATE TEMPORARY TABLE tmp_feishu_delete_users (
    id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (id)
) ENGINE = MEMORY;

CREATE TEMPORARY TABLE tmp_feishu_delete_departments (
    id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (id)
) ENGINE = MEMORY;

-- 包含有效和历史软删除数据，确保重新同步前彻底移除飞书来源记录。
INSERT INTO tmp_feishu_delete_users (id)
SELECT id
FROM sys_user
WHERE source_type = 'FEISHU'
  AND (@feishu_tenant_key IS NULL OR tenant_key = @feishu_tenant_key);

INSERT INTO tmp_feishu_delete_departments (id)
SELECT id
FROM sys_department
WHERE source_type = 'FEISHU'
  AND (@feishu_tenant_key IS NULL OR tenant_key = @feishu_tenant_key);

SELECT COUNT(*) INTO @target_user_count
FROM tmp_feishu_delete_users;

SELECT COUNT(*) INTO @target_department_count
FROM tmp_feishu_delete_departments;

-- 有效手工用户仍以目标飞书部门为主部门时阻止删除。
SELECT COUNT(*) INTO @blocking_primary_department_users
FROM sys_user AS system_user
JOIN tmp_feishu_delete_departments AS target_department
  ON target_department.id = system_user.primary_department_id
LEFT JOIN tmp_feishu_delete_users AS target_user
  ON target_user.id = system_user.id
WHERE system_user.deleted_at = 0
  AND target_user.id IS NULL;

-- 有效手工用户的数据范围仍引用目标飞书部门时阻止删除。
SELECT COUNT(*) INTO @blocking_department_scopes
FROM sys_user_department_scope AS department_scope
JOIN sys_user AS system_user
  ON system_user.id = department_scope.user_id
 AND system_user.deleted_at = 0
JOIN tmp_feishu_delete_departments AS target_department
  ON target_department.id = department_scope.department_id
LEFT JOIN tmp_feishu_delete_users AS target_user
  ON target_user.id = department_scope.user_id
WHERE department_scope.deleted_at = 0
  AND target_user.id IS NULL;

-- 有效手工部门挂在目标飞书部门下时阻止删除，避免留下断裂部门树。
SELECT COUNT(*) INTO @blocking_child_departments
FROM sys_department AS department
JOIN tmp_feishu_delete_departments AS target_department
  ON target_department.id = department.parent_id
WHERE department.deleted_at = 0
  AND department.source_type <> 'FEISHU';

SET @blocking_reference_count =
    @blocking_primary_department_users
    + @blocking_department_scopes
    + @blocking_child_departments;
SET @can_delete =
    IF(
        @confirm_feishu_physical_delete = 1
        AND @blocking_reference_count = 0,
        1,
        0
    );

SELECT
    @feishu_tenant_key AS tenant_filter,
    @target_department_count AS target_departments,
    @target_user_count AS target_users,
    @blocking_primary_department_users AS blocking_primary_department_users,
    @blocking_department_scopes AS blocking_department_scopes,
    @blocking_child_departments AS blocking_child_departments,
    @confirm_feishu_physical_delete AS confirm_flag,
    @can_delete AS will_execute;

START TRANSACTION;

-- 清除所有部门对目标飞书用户的负责人引用。
UPDATE sys_department AS department
JOIN tmp_feishu_delete_users AS target_user
  ON target_user.id = department.leader_user_id
SET department.leader_user_id = NULL
WHERE @can_delete = 1;
SET @cleared_department_leaders = ROW_COUNT();

DELETE user_role
FROM sys_user_role AS user_role
JOIN tmp_feishu_delete_users AS target_user
  ON target_user.id = user_role.user_id
WHERE @can_delete = 1;
SET @deleted_user_roles = ROW_COUNT();

DELETE department_scope
FROM sys_user_department_scope AS department_scope
LEFT JOIN tmp_feishu_delete_users AS target_user
  ON target_user.id = department_scope.user_id
LEFT JOIN tmp_feishu_delete_departments AS target_department
  ON target_department.id = department_scope.department_id
WHERE (target_user.id IS NOT NULL OR target_department.id IS NOT NULL)
  AND @can_delete = 1;
SET @deleted_department_scopes = ROW_COUNT();

DELETE ip_rule
FROM sys_ip_rule AS ip_rule
JOIN tmp_feishu_delete_users AS target_user
  ON target_user.id = ip_rule.user_id
WHERE ip_rule.scope_type = 2
  AND @can_delete = 1;
SET @deleted_personal_ip_rules = ROW_COUNT();

DELETE system_user
FROM sys_user AS system_user
JOIN tmp_feishu_delete_users AS target_user
  ON target_user.id = system_user.id
WHERE system_user.source_type = 'FEISHU'
  AND @can_delete = 1;
SET @deleted_users = ROW_COUNT();

DELETE department
FROM sys_department AS department
JOIN tmp_feishu_delete_departments AS target_department
  ON target_department.id = department.id
WHERE department.source_type = 'FEISHU'
  AND @can_delete = 1;
SET @deleted_departments = ROW_COUNT();

COMMIT;

SELECT
    IF(
        @can_delete = 1,
        'COMPLETED',
        'SKIPPED: set confirm flag to 1 and resolve blocking references'
    ) AS cleanup_status,
    @deleted_departments AS deleted_departments,
    @deleted_users AS deleted_users,
    @deleted_user_roles AS deleted_user_roles,
    @deleted_department_scopes AS deleted_department_scopes,
    @deleted_personal_ip_rules AS deleted_personal_ip_rules,
    @cleared_department_leaders AS cleared_department_leaders;

SELECT tenant_key, COUNT(*) AS remaining_feishu_departments
FROM sys_department
WHERE source_type = 'FEISHU'
  AND (@feishu_tenant_key IS NULL OR tenant_key = @feishu_tenant_key)
GROUP BY tenant_key;

SELECT tenant_key, COUNT(*) AS remaining_feishu_users
FROM sys_user
WHERE source_type = 'FEISHU'
  AND (@feishu_tenant_key IS NULL OR tenant_key = @feishu_tenant_key)
GROUP BY tenant_key;0

DROP TEMPORARY TABLE IF EXISTS tmp_feishu_delete_users;
DROP TEMPORARY TABLE IF EXISTS tmp_feishu_delete_departments;
