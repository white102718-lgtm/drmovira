package com.adpulse.main.manualtask;

import java.time.LocalDateTime;
import java.util.List;

/** 手动任务接口返回模型。 */
public final class ManualTaskViews {
    private ManualTaskViews() {}

    public record Action(
            String code,
            String name,
            String description,
            boolean dangerous,
            String confirmationText) {}

    public record Task(
            String code, String name, String description, boolean running, List<Action> actions) {}

    public record TriggerRequest(String actionCode, String confirmationText) {}

    public record Execution(
            String id,
            String taskCode,
            String taskName,
            String actionCode,
            String actionName,
            String status,
            String triggeredBy,
            String triggeredByName,
            LocalDateTime triggeredAt,
            LocalDateTime startedAt,
            LocalDateTime finishedAt,
            String logContent) {}

    public record Page(List<Execution> items, long total, int page, int pageSize) {}
}
