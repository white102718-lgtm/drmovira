-- 分配时固化使用团队，避免人员后续调动导致广告账户历史生命周期被当前组织关系覆盖。
ALTER TABLE ad_account_asset_assignment
    ADD COLUMN usage_team_name VARCHAR(100) NULL
        COMMENT '分配时使用人所属团队名称快照；历史迁移数据为执行迁移时的组织快照'
        AFTER user_name;

-- 存量记录无法还原分配当日组织，仅回填迁移时团队，并由接口按历史快照展示。
UPDATE ad_account_asset_assignment assignment
JOIN sys_user usage_user
    ON usage_user.id = assignment.user_id
LEFT JOIN sys_department department
    ON department.id = usage_user.primary_department_id
   AND department.deleted_at = 0
LEFT JOIN sys_department parent_department
    ON parent_department.id = department.parent_id
   AND parent_department.deleted_at = 0
SET assignment.usage_team_name = COALESCE(parent_department.dept_name, department.dept_name)
WHERE assignment.usage_team_name IS NULL;
