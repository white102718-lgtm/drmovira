-- 申请类型本身即为资源申请分类，移除历史兼容字段。
ALTER TABLE media_application_definition
    DROP COLUMN category;

ALTER TABLE media_application_type
    DROP COLUMN category;
