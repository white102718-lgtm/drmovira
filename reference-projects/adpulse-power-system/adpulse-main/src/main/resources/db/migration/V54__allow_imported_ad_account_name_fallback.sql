ALTER TABLE ad_account_asset
    MODIFY account_name VARCHAR(255) NOT NULL DEFAULT ''
        COMMENT '广告账户名称快照；优先由MongoDB fb_ad_accounts同步，平台名称缺失时允许Excel导入值兜底';
