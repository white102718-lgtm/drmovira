ALTER TABLE ad_account_asset
    ADD COLUMN remark VARCHAR(500) NULL
        COMMENT '广告账户资产人工备注；仅由台账编辑、批量修改或 Excel 导入维护'
        AFTER is_limited;
