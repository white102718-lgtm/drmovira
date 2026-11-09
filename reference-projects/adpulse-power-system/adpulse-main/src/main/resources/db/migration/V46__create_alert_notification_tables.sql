-- 预警配置、提醒记录与逐收件人投递记录均由 main 业务服务维护。
CREATE TABLE IF NOT EXISTS ad_alert_config (
    id BIGINT UNSIGNED NOT NULL COMMENT '固定为1的全局配置主键',
    enabled TINYINT(1) NOT NULL DEFAULT 0 COMMENT '自动预警总开关',
    ban_enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '封号数量预警开关',
    ban_threshold INT UNSIGNED NOT NULL DEFAULT 2 COMMENT '时间窗口内封号事件阈值',
    ban_window_value INT UNSIGNED NOT NULL DEFAULT 24 COMMENT '封号统计窗口数值',
    ban_window_unit VARCHAR(16) NOT NULL DEFAULT 'HOURS' COMMENT 'HOURS或DAYS',
    limit_change_enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '限额变化通知开关',
    spend_enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '账户消耗上限预警开关',
    spend_upper_limit DECIMAL(20, 4) NOT NULL DEFAULT 50000 COMMENT '各账户原币种消耗上限',
    spend_ratio DECIMAL(7, 4) NOT NULL DEFAULT 0.8 COMMENT '提醒比例，0到1',
    spend_window_value INT UNSIGNED NOT NULL DEFAULT 24 COMMENT '消耗统计窗口数值',
    spend_window_unit VARCHAR(16) NOT NULL DEFAULT 'HOURS' COMMENT 'HOURS或DAYS',
    updated_by BIGINT UNSIGNED NULL COMMENT '最后修改用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，软删除为Unix毫秒',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='广告账户全局预警配置';

INSERT INTO ad_alert_config (id) VALUES (1)
ON DUPLICATE KEY UPDATE id = VALUES(id);

CREATE TABLE IF NOT EXISTS ad_alert_recipient (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '收件人主键',
    recipient_type VARCHAR(16) NOT NULL COMMENT 'USER系统用户或CHAT飞书群',
    recipient_key VARCHAR(128) NOT NULL COMMENT '用户ID或飞书Chat ID',
    recipient_name VARCHAR(128) NOT NULL COMMENT '页面展示名称',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，软删除为Unix毫秒',
    PRIMARY KEY (id),
    UNIQUE KEY uk_alert_recipient (recipient_type, recipient_key, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='预警飞书收件人';

CREATE TABLE IF NOT EXISTS ad_alert_poll_cursor (
    event_type VARCHAR(32) NOT NULL COMMENT 'BAN或LIMIT_CHANGE',
    last_detected_at DATETIME(3) NULL COMMENT '最后已处理的Mongo事件时间',
    last_event_id VARCHAR(64) NULL COMMENT '同毫秒事件排序游标',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    PRIMARY KEY (event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Mongo变化事件消费游标';

CREATE TABLE IF NOT EXISTS ad_alert_notification (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '提醒记录主键',
    alert_type VARCHAR(32) NOT NULL COMMENT 'BAN_THRESHOLD、LIMIT_CHANGE或SPEND_THRESHOLD',
    dedupe_key VARCHAR(255) NOT NULL COMMENT '幂等键',
    title VARCHAR(255) NOT NULL COMMENT '提醒标题',
    content TEXT NOT NULL COMMENT '提醒正文',
    account_id VARCHAR(64) NULL COMMENT '单户提醒对应广告户ID',
    account_name VARCHAR(255) NULL COMMENT '广告户名称快照',
    trigger_value DECIMAL(20, 4) NULL COMMENT '触发值快照',
    threshold_value DECIMAL(20, 4) NULL COMMENT '阈值快照',
    currency VARCHAR(16) NULL COMMENT '账户原币种',
    source_event_id VARCHAR(64) NULL COMMENT 'Mongo变化事件ID',
    occurred_at DATETIME(3) NOT NULL COMMENT '业务事件或评估发生时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_alert_notification_dedupe (dedupe_key),
    KEY idx_alert_notification_time (created_at, id),
    KEY idx_alert_notification_type (alert_type, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每次实际预警提醒记录';

CREATE TABLE IF NOT EXISTS ad_alert_delivery (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '投递记录主键',
    notification_id BIGINT UNSIGNED NOT NULL COMMENT '逻辑关联ad_alert_notification',
    recipient_type VARCHAR(16) NOT NULL COMMENT 'USER或CHAT',
    recipient_key VARCHAR(128) NOT NULL COMMENT '用户ID或Chat ID',
    recipient_name VARCHAR(128) NOT NULL COMMENT '收件人名称快照',
    delivery_status VARCHAR(16) NOT NULL COMMENT 'SUCCESS、FAILED或SKIPPED',
    error_message VARCHAR(500) NULL COMMENT '失败原因',
    delivered_at DATETIME(3) NULL COMMENT '成功投递时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录时间',
    PRIMARY KEY (id),
    KEY idx_alert_delivery_notification (notification_id, id),
    KEY idx_alert_delivery_status (delivery_status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='预警逐收件人飞书投递记录';
