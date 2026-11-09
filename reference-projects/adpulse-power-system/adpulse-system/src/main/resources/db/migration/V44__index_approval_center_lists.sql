-- 审批中心按有效状态读取待审批、待办理申请，索引同时保持倒序列表的稳定主键路径。
CREATE INDEX idx_media_application_status_list
    ON media_asset_application (status, deleted_at, id);

-- 审批列表批量回填已分配资产，按申请关联键查询并保持资产 ID 顺序。
CREATE INDEX idx_media_asset_application_list
    ON media_asset (application_id, deleted_at, id);
