CREATE TABLE IF NOT EXISTS fb_ad_channel (
    `id`                 INT                NOT NULL          COMMENT "渠道ID",
    `channel_name`       VARCHAR(100)       NOT NULL          COMMENT "渠道名称",
    `service_fee`        DECIMAL(10,2)      NULL              COMMENT "服务费",
    `activation_fee`     DECIMAL(10,2)      NULL              COMMENT "开户费",
    `rebate_rate`        DECIMAL(5,2)       NULL              COMMENT "返点/折扣比例",
    `settlement_method`  VARCHAR(200)       NULL              COMMENT "结算方式/要求",
    `total_consumption`  DECIMAL(12,2)      NULL              COMMENT "账户总消耗",
    `usage_status`       VARCHAR(50)        NULL              COMMENT "使用情况",
    `payment_address`    STRING             NULL              COMMENT "收款地址",
    `login_url`          VARCHAR(255)       NULL              COMMENT "登录/对接链接",
    `remark`             STRING             NULL              COMMENT "备注",
    `status`             TINYINT            NULL DEFAULT "1"  COMMENT "状态(0-禁用 1-启用)",
    `create_time`        DATETIME           NULL              COMMENT "创建时间",
    `channel_type`       INT                NULL              COMMENT "渠道类型 1代理商 2号商",
    `channel_short_name` VARCHAR(32)        NULL              COMMENT "渠道简称",
    `channel_code`       VARCHAR(32)        NULL              COMMENT "渠道编码",
    `belong_team`        VARCHAR(64)        NULL              COMMENT "所属团队",
    `account_ids_json`   JSON               NULL              COMMENT "渠道下FB账户信息(JSON)"
  ) ENGINE=OLAP
  UNIQUE KEY(`id`)
  COMMENT "渠道_账户信息表"
  DISTRIBUTED BY HASH(`id`) BUCKETS AUTO
  PROPERTIES (
    "replication_num" = "1",
    "enable_unique_key_merge_on_write" = "true"
  );