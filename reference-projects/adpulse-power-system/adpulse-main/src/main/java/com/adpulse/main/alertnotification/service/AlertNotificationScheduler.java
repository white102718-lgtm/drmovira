package com.adpulse.main.alertnotification.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** 按各预警类型约定的频率评估启用规则。 */
@Component
public class AlertNotificationScheduler {
    private static final Logger log = LoggerFactory.getLogger(AlertNotificationScheduler.class);
    private final AlertNotificationService service;

    public AlertNotificationScheduler(AlertNotificationService service) {
        this.service = service;
    }

    @Scheduled(cron = "0 * * * * *", zone = "Asia/Shanghai")
    public void evaluateLimitChanges() {
        try {
            service.evaluateLimitChanges();
        } catch (RuntimeException exception) {
            log.error("限额变化通知评估失败", exception);
        }
    }

    /** 封户提醒按北京时间整点统计上一个完整自然小时，避免轮询漂移造成遗漏或重复。 */
    @Scheduled(cron = "0 0 * * * *", zone = "Asia/Shanghai")
    public void evaluateHourlyBanAlerts() {
        try {
            service.evaluateHourlyBan();
        } catch (RuntimeException exception) {
            log.error("封户小时提醒评估失败", exception);
        }
    }

    @Scheduled(cron = "0 0 10 * * *", zone = "Asia/Shanghai")
    public void evaluateMorningBanSummary() {
        try {
            service.evaluateMorningBanSummary();
        } catch (RuntimeException exception) {
            log.error("10点封户汇总评估失败", exception);
        }
    }

    @Scheduled(cron = "0 30 18 * * *", zone = "Asia/Shanghai")
    public void evaluateEveningBanSummary() {
        try {
            service.evaluateEveningBanSummary();
        } catch (RuntimeException exception) {
            log.error("18点30分封户汇总评估失败", exception);
        }
    }

    /** 24:00 由次日 00:00 触发，业务查询范围固定为前一完整自然日。 */
    @Scheduled(cron = "0 0 0 * * *", zone = "Asia/Shanghai")
    public void evaluatePreviousDayBanSummary() {
        try {
            service.evaluatePreviousDayBanSummary();
        } catch (RuntimeException exception) {
            log.error("24点封户汇总评估失败", exception);
        }
    }
}
