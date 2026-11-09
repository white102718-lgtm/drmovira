-- 素材师结算按月份填写；保留历史规则 ID 和审批编码，只迁移展示名称与周期。
SET NAMES utf8mb4;

UPDATE sys_daily_report_rule
SET name = '素材师月报',
    config_json = JSON_SET(
        config_json,
        '$.name',
        '素材师月报',
        '$.period',
        '每月',
        '$.schedule.submissionDays',
        JSON_ARRAY(),
        '$.schedule.submissionDayOfMonth',
        CASE
            WHEN CAST(
                JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.schedule.submissionDayOfMonth'))
                AS UNSIGNED
            ) BETWEEN 1 AND 28
                THEN CAST(
                    JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.schedule.submissionDayOfMonth'))
                    AS UNSIGNED
                )
            ELSE 1
        END
    )
WHERE rule_key = 'material-designer-daily-report'
  AND deleted_at = 0;

UPDATE media_approval_config
SET flow_name = '素材师月报申请',
    description = '提交素材师结算月报并关联投放师、项目和任务线。'
WHERE asset_type = 'MATERIAL_DESIGNER_DAILY_REPORT'
  AND deleted_at = 0;

UPDATE media_application_definition
SET application_name = '素材师月报申请',
    description = '提交素材师结算月报并关联投放师、项目和任务线。'
WHERE application_code = 'MATERIAL_DESIGNER_DAILY_REPORT'
  AND deleted_at = 0;
