package com.adpulse.main.alertnotification.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.annotation.Scheduled;

import java.lang.reflect.Method;

/** 预警通知任务执行时点配置测试。 */
class AlertNotificationSchedulerTest {

    @Test
    void shouldScheduleBanSummariesAtConfiguredBeijingTimes() throws Exception {
        assertSchedule("evaluateMorningBanSummary", "0 0 10 * * *");
        assertSchedule("evaluateEveningBanSummary", "0 30 18 * * *");
        assertSchedule("evaluatePreviousDayBanSummary", "0 0 0 * * *");
    }

    private void assertSchedule(String methodName, String cron) throws Exception {
        Method method = AlertNotificationScheduler.class.getMethod(methodName);
        Scheduled scheduled = method.getAnnotation(Scheduled.class);

        assertThat(scheduled).isNotNull();
        assertThat(scheduled.cron()).isEqualTo(cron);
        assertThat(scheduled.zone()).isEqualTo("Asia/Shanghai");
    }
}
