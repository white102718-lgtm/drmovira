-- 部署前人工执行：日报Google推送改用服务账户，保留历史OAuth账号ID但不再新增写入。
ALTER TABLE biz_delivery_report_google_template
    MODIFY google_account_id BIGINT UNSIGNED NULL
        COMMENT '历史OAuth账号ID；服务账户模式不再写入';

ALTER TABLE biz_delivery_report_google_push_item
    MODIFY google_account_id BIGINT UNSIGNED NULL
        COMMENT '历史OAuth账号ID；服务账户模式不再写入';
