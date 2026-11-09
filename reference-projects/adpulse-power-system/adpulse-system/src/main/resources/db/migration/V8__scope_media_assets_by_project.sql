ALTER TABLE media_asset
    ADD COLUMN project_id VARCHAR(64) NULL COMMENT '归属项目稳定标识' AFTER asset_code,
    ADD COLUMN project_name VARCHAR(128) NULL COMMENT '归属项目名称快照' AFTER project_id,
    ADD KEY idx_media_asset_project (project_id, asset_type, status, deleted_at);

