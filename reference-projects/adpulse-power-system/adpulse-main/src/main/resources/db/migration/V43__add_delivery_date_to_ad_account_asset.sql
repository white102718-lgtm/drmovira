ALTER TABLE ad_account_asset
    ADD COLUMN delivery_date DATE NULL COMMENT '广告账户下户日期；由飞书广告账户使用记录同步，NULL 表示未下户或未维护';
