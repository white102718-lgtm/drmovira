package com.adpulse.main.manualtask;

import com.adpulse.main.manualtask.ManualTaskModels.Execution;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** 领取并执行已入队的手动任务，HTTP 请求只负责创建触发事件。 */
@Component
public class ManualTaskWorker {
    private static final Logger LOGGER = LoggerFactory.getLogger(ManualTaskWorker.class);
    private static final DateTimeFormatter LOG_TIME =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS");
    private static final ZoneId BEIJING = ZoneId.of("Asia/Shanghai");
    private final ManualTaskMapper mapper;
    private final ManualTaskService service;

    public ManualTaskWorker(ManualTaskMapper mapper, ManualTaskService service) {
        this.mapper = mapper;
        this.service = service;
    }

    @Scheduled(fixedDelayString = "${adpulse.manual-task.worker-delay-ms:2000}")
    public void consume() {
        for (Execution execution : mapper.findPending(service.definitionCodes(), 5)) {
            if (mapper.claim(execution.getId()) != 1) continue;
            run(execution);
        }
    }

    /** 将长期无心跳的运行记录置为失败，避免服务中断后永久占用任务活动槽。 */
    @Scheduled(fixedDelayString = "${adpulse.manual-task.stale-check-delay-ms:60000}")
    public void failStaleExecutions() {
        LocalDateTime before = LocalDateTime.now().minusMinutes(30);
        String content =
                "[" + LOG_TIME.format(LocalDateTime.now(BEIJING)) + "] [ERROR] 服务中断或执行超时，任务已自动结束\n";
        for (Execution execution : mapper.findStaleRunning(before)) {
            if (mapper.failStale(execution.getId(), before, content) == 1) {
                LOGGER.warn("Marked stale manual task execution {} as failed", execution.getId());
            }
        }
    }

    private void run(Execution execution) {
        ManualTaskLog log = new ManualTaskLog(execution.getId(), mapper);
        try {
            ManualTaskDefinition definition = service.definition(execution.getTaskCode());
            if (definition == null)
                throw new IllegalStateException("任务定义不存在：" + execution.getTaskCode());
            log.info("开始执行任务，触发人：" + execution.getTriggeredByName());
            definition.execute(
                    new ManualTaskContext(execution.getId(), execution.getTriggeredBy(), log),
                    execution.getActionCode());
            log.info("任务执行成功");
            mapper.complete(execution.getId(), "SUCCESS");
        } catch (Exception exception) {
            log.error(
                    exception.getClass().getSimpleName()
                            + "："
                            + String.valueOf(exception.getMessage()));
            mapper.complete(execution.getId(), "FAILED");
            LOGGER.error(
                    "Manual task {} execution {} failed",
                    execution.getTaskCode(),
                    execution.getId(),
                    exception);
        }
    }
}
