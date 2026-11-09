-- 重提申请保留上一张被驳回申请的稳定 ID，供详情追溯；不建立数据库外键，引用有效性由审批服务校验。
ALTER TABLE media_asset_application
    ADD COLUMN source_application_id BIGINT UNSIGNED NULL
        COMMENT '重提来源申请 ID；仅重提单记录上一张已驳回申请的逻辑关联'
        AFTER nodes_snapshot,
    ADD KEY idx_media_asset_application_source (source_application_id, deleted_at);
