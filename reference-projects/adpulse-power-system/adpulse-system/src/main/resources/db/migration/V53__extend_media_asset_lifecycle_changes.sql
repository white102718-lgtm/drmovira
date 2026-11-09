ALTER TABLE media_asset_lifecycle_event
    ADD COLUMN update_source VARCHAR(32) NULL COMMENT '资料更新来源' AFTER description,
    ADD COLUMN changes_json JSON NULL COMMENT '结构化字段差异；敏感凭据仅保存设置状态' AFTER update_source;
