-- 申请单固化提交人当时的主部门，后续组织调动不影响审批历史的展示与筛选。
ALTER TABLE media_asset_application
    ADD COLUMN department_id BIGINT UNSIGNED NULL
        COMMENT '申请人提交时的主部门 ID 快照，逻辑关联 sys_department.id'
        AFTER requester_name,
    ADD COLUMN department_name VARCHAR(128) NULL
        COMMENT '申请人提交时的主部门名称快照'
        AFTER department_id,
    ADD KEY idx_media_application_department (department_id, status, deleted_at);

-- 历史申请优先沿用已保存的 JSON 快照；没有快照时按申请人当前主部门补齐。
UPDATE media_asset_application a
JOIN sys_user u
  ON u.id = a.requester_id
 AND u.status = 1
 AND u.deleted_at = 0
JOIN sys_department d
  ON d.id = u.primary_department_id
 AND d.status = 1
 AND d.deleted_at = 0
SET a.department_id = COALESCE(
        a.department_id,
        CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(a.form_data, '$._requesterDepartmentId')), 'null') AS UNSIGNED),
        d.id
    ),
    a.department_name = COALESCE(
        NULLIF(a.department_name, ''),
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(a.form_data, '$._requesterDepartmentName')), 'null'),
        d.dept_name
    )
WHERE a.deleted_at = 0
  AND (a.department_id IS NULL OR a.department_name IS NULL OR a.department_name = '');
