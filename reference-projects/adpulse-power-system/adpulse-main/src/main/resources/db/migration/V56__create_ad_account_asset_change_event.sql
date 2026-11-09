CREATE TABLE IF NOT EXISTS ad_account_asset_change_event (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '资料更新事件主键',
    ad_account_asset_id BIGINT NOT NULL COMMENT '广告账户资产主键快照',
    account_id VARCHAR(64) NOT NULL COMMENT '广告账户ID快照',
    update_source VARCHAR(32) NOT NULL COMMENT '更新来源：MANUAL_EDIT/EXCEL_IMPORT/EXCEL_BATCH/BATCH_EDIT',
    actor_id BIGINT NULL COMMENT '操作人用户ID快照',
    actor_name VARCHAR(128) NOT NULL COMMENT '操作人名称快照',
    changes_json JSON NOT NULL COMMENT '全部实际字段差异；敏感凭据仅保存设置状态',
    occurred_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '事件发生时间',
    PRIMARY KEY (id),
    KEY idx_ad_account_asset_change_event_asset_time
        (ad_account_asset_id, occurred_at, id),
    KEY idx_ad_account_asset_change_event_account_time
        (account_id, occurred_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='广告账户资料更新审计事件';
