-- 审批中心按当前操作人查询已审批记录，避免全表扫描审批轨迹。
CREATE INDEX idx_media_approval_log_actor_action_application
    ON media_asset_approval_log (actor_id, action, application_id);
