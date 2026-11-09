-- 确保手工执行迁移时，中文菜单与说明字段按 UTF-8 写入数据库。
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS sys_daily_report_rule (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '日报规则主键',
    rule_key VARCHAR(64) NOT NULL COMMENT '前端稳定规则标识',
    name VARCHAR(100) NOT NULL COMMENT '规则名称快照索引',
    config_json JSON NOT NULL COMMENT '字段、人员、时区、周期、提交日、截止与提醒配置',
    reminder_enabled TINYINT NOT NULL DEFAULT 0 COMMENT '是否启用服务端提醒任务',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '1启用，0停用',
    created_by BIGINT UNSIGNED NOT NULL,
    updated_by BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_daily_report_rule_key_deleted (rule_key, deleted_at),
    KEY idx_daily_report_rule_reminder (status, reminder_enabled, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='日报规则；配置由服务端持久化并用于权限与提醒计算';

CREATE TABLE IF NOT EXISTS sys_daily_report_submission (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '日报提交主键',
    rule_id BIGINT UNSIGNED NOT NULL COMMENT '关联日报规则',
    report_date DATE NOT NULL COMMENT '按规则时区计算的业务提交日期',
    field_values_json JSON NOT NULL COMMENT '提交字段值',
    attachments_json JSON NULL COMMENT '字段到上传文件的绑定快照',
    rule_snapshot_json JSON NOT NULL COMMENT '提交时规则快照，历史可追溯',
    submitted_by_id BIGINT UNSIGNED NOT NULL,
    submitted_by_name VARCHAR(100) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_daily_report_submission_rule_date_user (rule_id, report_date, submitted_by_id),
    KEY idx_daily_report_submission_user_time (submitted_by_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='日报提交记录；记录字段、附件与规则快照';

CREATE TABLE IF NOT EXISTS sys_daily_report_file_binding (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    submission_id BIGINT UNSIGNED NOT NULL,
    file_id BIGINT UNSIGNED NOT NULL,
    sort_order INT UNSIGNED NOT NULL DEFAULT 0,
    created_by BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_daily_report_submission_file_deleted (submission_id, file_id, deleted_at),
    KEY idx_daily_report_file_submission (submission_id, deleted_at, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='日报与通用上传文件绑定';

CREATE TABLE IF NOT EXISTS sys_daily_report_reminder_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    rule_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    report_date DATE NOT NULL COMMENT '规则时区下应提交的业务日期',
    reminder_time VARCHAR(5) NOT NULL COMMENT '规则时区下触发时间HH:mm',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_daily_report_reminder_once (rule_id, user_id, report_date, reminder_time),
    KEY idx_daily_report_reminder_rule_date (rule_id, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='服务端日报提醒去重记录';

SET @system_menu_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'SystemManagement' AND deleted_at = 0 LIMIT 1
);

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    icon, permission_code, visible, cacheable, sort_order, status, remark
) SELECT
    @system_menu_id, 2, 'SystemDailyReportConfig', '日报配置',
    '/system-management/daily-report-config', '/system/daily-report-config',
    'lucide:calendar-check-2', 'system:daily-report:manage', 1, 0, 61, 1,
    '管理日报字段、范围、时区和服务端提醒任务'
WHERE NOT EXISTS (
    SELECT 1
    FROM sys_menu
    WHERE menu_code = 'SystemDailyReportConfig'
      AND deleted_at = 0
);

-- 部分测试库已经存在同编码的旧菜单，必须回填其权限码，确保管理员可实际配置日报规则。
UPDATE sys_menu
SET parent_id = @system_menu_id,
    menu_type = 2,
    menu_name = '日报配置',
    route_path = '/system-management/daily-report-config',
    component = '/system/daily-report-config',
    icon = 'lucide:calendar-check-2',
    permission_code = 'system:daily-report:manage',
    visible = 1,
    cacheable = 0,
    sort_order = 61,
    status = 1,
    remark = '管理日报字段、范围、时区和服务端提醒任务'
WHERE menu_code = 'SystemDailyReportConfig'
  AND deleted_at = 0;

SET @daily_report_manage_menu_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'SystemDailyReportConfig'
      AND deleted_at = 0
    LIMIT 1
);

INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT role.id, @daily_report_manage_menu_id
FROM sys_role role
WHERE role.role_code = 'ADMIN' AND role.deleted_at = 0;
