package com.adpulse.system.feishuorg.service;

import java.time.Duration;
import java.util.concurrent.ScheduledFuture;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.SmartLifecycle;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Component;

/** 独立调度线程避免组织全量拉取阻塞日报等已有任务。 */
@Component
public class FeishuOrganizationScheduler implements SmartLifecycle {
    private final FeishuOrganizationJobService service;
    private final TaskScheduler scheduler;
    private ScheduledFuture<?> dueTask;
    private ScheduledFuture<?> consumeTask;
    private volatile boolean running;

    public FeishuOrganizationScheduler(
            FeishuOrganizationJobService service,
            @Qualifier("feishuOrganizationTaskScheduler") TaskScheduler scheduler) {
        this.service = service;
        this.scheduler = scheduler;
    }

    /** 只注册组织任务，避免启用系统服务内其他尚未开启的注解调度。 */
    @Override
    public void start() {
        if (running) return;
        dueTask = scheduler.scheduleWithFixedDelay(service::scheduleDue, Duration.ofMinutes(1));
        consumeTask = scheduler.scheduleWithFixedDelay(service::consumeOne, Duration.ofSeconds(5));
        running = true;
    }

    /** 停止新调度；未完成任务由持久化租约进行超时恢复。 */
    @Override
    public void stop() {
        if (dueTask != null) dueTask.cancel(false);
        if (consumeTask != null) consumeTask.cancel(false);
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
