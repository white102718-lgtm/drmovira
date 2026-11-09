-- 申请入口可在资源申请页单独隐藏；隐藏不影响日报等专用入口继续使用其审批配置。
ALTER TABLE media_application_definition
    ADD COLUMN show_in_resource_application TINYINT NOT NULL DEFAULT 1
        COMMENT '是否在资源申请页展示：1展示，0隐藏'
        AFTER visibility;

-- 固定日报由日报页面填写并提交审批，不应作为资源申请入口展示。
UPDATE media_application_definition
SET show_in_resource_application = 0
WHERE application_code IN ('DELIVERY_DAILY_REPORT', 'MATERIAL_DESIGNER_DAILY_REPORT')
  AND deleted_at = 0;
