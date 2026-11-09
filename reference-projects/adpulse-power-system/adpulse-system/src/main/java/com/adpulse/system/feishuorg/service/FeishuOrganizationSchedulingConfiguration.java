package com.adpulse.system.feishuorg.service;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

/** 为组织调度和任务消费提供独立线程，不改变其他业务调度配置。 */
@Configuration
public class FeishuOrganizationSchedulingConfiguration {
    /** 两个线程分别用于到期扫描和任务消费。 */
    @Bean
    public ThreadPoolTaskScheduler feishuOrganizationTaskScheduler() {
        var scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("feishu-org-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
}
