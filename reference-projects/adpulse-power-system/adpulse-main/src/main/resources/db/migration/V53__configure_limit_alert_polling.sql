-- 限额变化通知按用户配置的固定分钟窗口查询；提醒表的事件幂等键负责防止重复投递。
ALTER TABLE ad_alert_config
    ADD COLUMN limit_poll_interval_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 15
        COMMENT '限额变化轮询间隔（分钟）：5、10、15、30或60'
        AFTER limit_change_enabled,
    ADD COLUMN limit_change_enabled_at DATETIME(3) NULL
        COMMENT '本轮限额通知启用时间（北京时间），用于排除关闭期间事件'
        AFTER limit_poll_interval_minutes;

UPDATE ad_alert_config
SET limit_change_enabled_at = CASE
    WHEN enabled = 1 AND limit_change_enabled = 1 THEN CURRENT_TIMESTAMP(3)
    ELSE NULL
END
WHERE deleted_at = 0;

-- 限额通知不再保存消费进度；停机超过配置窗口时允许忽略过期事件。
DROP TABLE IF EXISTS ad_alert_poll_cursor;
