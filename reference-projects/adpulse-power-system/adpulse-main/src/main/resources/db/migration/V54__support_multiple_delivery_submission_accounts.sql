ALTER TABLE biz_delivery_submission_object
    DROP CHECK ck_delivery_object_type,
    ADD CONSTRAINT ck_delivery_object_type
        CHECK (object_type IN ('ACCOUNT', 'CAMPAIGN', 'AD_SET', 'AD'));

ALTER TABLE biz_delivery_submission_object
    MODIFY COLUMN object_type VARCHAR(20) NOT NULL
        COMMENT '交付对象类型：ACCOUNT/CAMPAIGN/AD_SET/AD',
    MODIFY COLUMN object_id VARCHAR(200) NOT NULL
        COMMENT '平台账户或广告对象ID';
