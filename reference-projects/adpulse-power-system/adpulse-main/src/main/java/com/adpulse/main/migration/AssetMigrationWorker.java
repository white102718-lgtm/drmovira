package com.adpulse.main.migration;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 使用独立线程执行迁移，不占用 HTTP 请求线程或现有飞书定时任务线程。 */
public class AssetMigrationWorker {
    private static final Logger LOG = LoggerFactory.getLogger(AssetMigrationWorker.class);
    private final AssetMigrationService service;
    private final ScheduledExecutorService executor =
            Executors.newSingleThreadScheduledExecutor(
                    runnable ->
                            Thread.ofPlatform()
                                    .name("legacy-asset-migration")
                                    .daemon(true)
                                    .unstarted(runnable));

    public AssetMigrationWorker(AssetMigrationService service) {
        this.service = service;
    }

    /** 启动持久化任务轮询，重启时继续已提交批次之后的工作。 */
    @PostConstruct
    public void start() {
        executor.scheduleWithFixedDelay(
                () -> {
                    try {
                        service.tick();
                    } catch (RuntimeException exception) {
                        LOG.warn("账户迁移工作器暂不可用，错误类型={}", exception.getClass().getSimpleName());
                    }
                },
                2,
                2,
                TimeUnit.SECONDS);
    }

    /** 停止取新批次，给当前事务留出提交或回滚时间。 */
    @PreDestroy
    public void stop() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(25, TimeUnit.SECONDS)) executor.shutdownNow();
        } catch (InterruptedException exception) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
