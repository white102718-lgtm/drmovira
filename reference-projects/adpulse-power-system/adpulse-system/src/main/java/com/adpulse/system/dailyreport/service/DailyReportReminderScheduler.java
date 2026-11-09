package com.adpulse.system.dailyreport.service;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** 由主服务的 @EnableScheduling 驱动；提醒状态和去重均在数据库中持久化。 */
@Component
public class DailyReportReminderScheduler {
    private final DailyReportService service;

    public DailyReportReminderScheduler(DailyReportService service) {
        this.service = service;
    }

    @Scheduled(fixedDelayString = "${adpulse.daily-report.reminder-delay-ms:60000}")
    public void dispatchDueReminders() {
        service.dispatchDueReminders();
    }
}
