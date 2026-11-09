-- 申请入口先独立创建，审批配置发布时再建立关联；未关联申请不会出现在申请中心。
ALTER TABLE media_application_definition
    MODIFY approval_config_id BIGINT UNSIGNED NULL
        COMMENT '关联审批配置 ID；未关联时为 NULL，逻辑关联 media_approval_config.id';
