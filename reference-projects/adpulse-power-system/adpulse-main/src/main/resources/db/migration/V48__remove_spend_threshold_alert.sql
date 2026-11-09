-- 消耗上限预警已下线；先清理逻辑关联的投递记录，再删除提醒与废弃配置字段。
DELETE delivery
FROM ad_alert_delivery delivery
INNER JOIN ad_alert_notification notification
    ON notification.id = delivery.notification_id
WHERE notification.alert_type = 'SPEND_THRESHOLD';

DELETE FROM ad_alert_notification
WHERE alert_type = 'SPEND_THRESHOLD';

ALTER TABLE ad_alert_config
    DROP COLUMN spend_enabled,
    DROP COLUMN spend_upper_limit,
    DROP COLUMN spend_ratio,
    DROP COLUMN spend_window_value,
    DROP COLUMN spend_window_unit;

ALTER TABLE ad_alert_notification
    MODIFY COLUMN alert_type VARCHAR(32) NOT NULL
        COMMENT '提醒类型：BAN_THRESHOLD封户小时提醒、LIMIT_CHANGE限额变化通知';
