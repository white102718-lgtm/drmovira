package com.adpulse.main.manualtask;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

/** 将任务过程日志实时追加到触发事件的 LONGTEXT 字段。 */
public final class ManualTaskLog {
    private static final DateTimeFormatter FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS");
    private static final ZoneId BEIJING = ZoneId.of("Asia/Shanghai");
    private final Long executionId;
    private final ManualTaskMapper mapper;

    public ManualTaskLog(Long executionId, ManualTaskMapper mapper) {
        this.executionId = executionId;
        this.mapper = mapper;
    }

    public void info(String message) {
        append("INFO", message);
    }

    public void warn(String message) {
        append("WARN", message);
    }

    public void error(String message) {
        append("ERROR", message);
    }

    private void append(String level, String message) {
        String safe = message == null ? "" : message.replace("\r", " ").replace("\n", " ");
        mapper.appendLog(
                executionId,
                "["
                        + FORMATTER.format(LocalDateTime.now(BEIJING))
                        + "] ["
                        + level
                        + "] "
                        + safe
                        + "\n");
    }
}
