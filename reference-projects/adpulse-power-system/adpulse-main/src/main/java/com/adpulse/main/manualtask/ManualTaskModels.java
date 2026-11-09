package com.adpulse.main.manualtask;

import java.time.LocalDateTime;
import lombok.Data;

/** 手动任务持久化模型。 */
public final class ManualTaskModels {
    private ManualTaskModels() {}

    /** 一次人工触发产生的执行事件。 */
    @Data
    public static class Execution {
        private Long id;
        private String taskCode;
        private String taskName;
        private String actionCode;
        private String actionName;
        private String status;
        private Long triggeredBy;
        private String triggeredByName;
        private LocalDateTime triggeredAt;
        private LocalDateTime startedAt;
        private LocalDateTime finishedAt;
        private LocalDateTime heartbeatAt;
        private String logContent;
    }

    /** 名称匹配所需的系统用户字段。 */
    @Data
    public static class UserCandidate {
        private Long id;
        private String username;
        private String displayName;
        private String realName;
    }

    /** 单账户写入结果。 */
    public record AssignmentResult(boolean assetFound, int added, int existing) {}
}
