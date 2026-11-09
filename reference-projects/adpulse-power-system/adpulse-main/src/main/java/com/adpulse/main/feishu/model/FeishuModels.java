package com.adpulse.main.feishu.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 飞书同步持久化模型。 */
public final class FeishuModels {
    private FeishuModels() {}

    /** 飞书应用配置持久化模型。 */
    @Data
    public static class Config {
        private Long id;
        private String appName;
        private String appId;
        private String appSecretCiphertext;
        private Long updatedBy;
    }

    /** 飞书任务持久化模型。 */
    @Data
    public static class Task {
        private Long id;
        private String taskName;
        private String appId;
        private String appToken;
        private String tableId;
        private String tableName;
        private String targetTableName;
        private Integer taskType;
        private Integer status;
        private LocalDateTime lastSyncTime;
        private LocalDateTime createdAt;
    }

    /** 飞书字段映射持久化模型。 */
    @Data
    public static class Mapping {
        private Long id;
        private Long taskId;
        private String systemFieldName;
        private String feishuFieldName;
        private String columnComment;
        private String dataType;
        private Integer isRequired;
        private Integer isSplit;
    }

    /** 飞书同步日志持久化模型。 */
    @Data
    public static class Log {
        private Long id;
        private Integer status;
        private Integer totalCount;
        private Integer successCount;
        private Integer failCount;
        private String errorMessage;
        private LocalDateTime startedAt;
        private LocalDateTime endedAt;
    }
}
