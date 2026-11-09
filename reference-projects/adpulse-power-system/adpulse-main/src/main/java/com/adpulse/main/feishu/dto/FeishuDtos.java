package com.adpulse.main.feishu.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDateTime;
import java.util.List;

/** 飞书同步接口请求与响应。 */
public final class FeishuDtos {
    private FeishuDtos() {}

    /** 飞书应用凭证保存请求。 */
    public record ConfigSave(@NotBlank String appName, @NotBlank String appId, String appSecret) {}

    /** 不回显密钥的飞书应用配置。 */
    public record Config(String id, String appName, String appId) {}

    /** 飞书同步任务保存请求。 */
    public record TaskSave(
            @NotBlank String taskName,
            @NotBlank String appId,
            @NotBlank String appToken,
            @NotBlank String tableId,
            String tableName,
            @NotBlank String targetTableName,
            @NotNull Integer taskType,
            @NotNull Integer status) {}

    /** 飞书同步任务。 */
    public record Task(
            String taskId,
            String taskName,
            String appId,
            String appToken,
            String tableId,
            String tableName,
            String targetTableName,
            Integer taskType,
            Integer status,
            LocalDateTime lastSyncTime,
            LocalDateTime createTime) {}

    /** 任务状态保存请求。 */
    public record StatusSave(@NotNull Integer status) {}

    /** 字段映射保存请求和响应。 */
    public record Mapping(
            String id,
            String taskId,
            @NotBlank String systemFieldName,
            @NotBlank String feishuFieldName,
            String columnComment,
            String dataType,
            Integer isRequired,
            Integer isSplit) {}

    /** 同步执行日志。 */
    public record Log(
            String id,
            Integer status,
            Integer totalCount,
            Integer successCount,
            Integer failCount,
            String errMsg,
            LocalDateTime startTime,
            LocalDateTime endTime) {}

    /** 飞书表格发现请求。 */
    public record DiscoverSave(
            String appId, @NotBlank String appTokenOrUrl, @NotNull Integer taskType) {}

    /** 飞书子表选项。 */
    public record TableOption(String tableId, String name) {}

    /** 飞书表格发现响应。 */
    public record Discovery(String appToken, List<TableOption> tables) {}

    /** 飞书字段选项。 */
    public record FieldOption(String fieldName, String name) {}

    /** 系统表字段选项。 */
    public record SystemColumn(String columnName, String columnComment) {}
}
