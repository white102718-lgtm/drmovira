ALTER TABLE media_asset
    ADD COLUMN channel_id VARCHAR(64) NULL
        COMMENT '资产来源渠道稳定 ID；对应渠道管理中的渠道记录，不建立跨服务外键'
        AFTER project_name,
    ADD COLUMN channel_name VARCHAR(128) NULL
        COMMENT '资产入库时的渠道名称快照；渠道改名后仍保留原始业务口径'
        AFTER channel_id,
    ADD KEY idx_media_asset_channel (channel_id, deleted_at);
