package com.adpulse.system.feishuorg.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.List;

/** 飞书组织同步接口视图。 */
public final class FeishuOrganizationViews {

    private FeishuOrganizationViews() {}

    /** 飞书应用配置保存请求。 */
    public record ApplicationConfigSave(
            @NotBlank String appName, @NotBlank String appId, String appSecret) {}

    /** 不回显App Secret的飞书应用配置。 */
    public record ApplicationConfig(String id, String appName, String appId) {}

    /** 保存自动同步频率和缺失停用保护；启用时必须提供近期预览。 */
    public record ScheduleSave(
            boolean enabled,
            @Min(0) @Max(60) int intervalMinutes,
            @NotNull @Pattern(regexp = "([01][0-9]|2[0-3]):[0-5][0-9]") String dailyTime,
            @Min(1) @Max(100000) int missingCountLimit,
            @Min(1) @Max(100) int missingPercentLimit,
            String previewId) {}

    /** 自动同步配置；执行时间携带北京时间偏移，避免浏览器时区歧义。 */
    public record ScheduleView(
            boolean enabled,
            int intervalMinutes,
            String dailyTime,
            int missingCountLimit,
            int missingPercentLimit,
            OffsetDateTime nextRunAt) {}

    /** 预览编号绑定操作者、应用和快照，人工确认不能使用过期或变化的快照。 */
    public record Preview(String previewId, SyncResult result, boolean requiresReview) {}

    /** 手动提交任务；缺失停用超限时需要显式确认。 */
    public record SyncRequest(
            @NotBlank @Pattern(regexp = "[0-9]{1,19}") String previewId, boolean acceptMissing) {}

    /** 已持久化的异步同步任务。 */
    public record SyncSubmission(String id, String status) {}

    /** 同步预览或执行结果。 */
    public record SyncResult(
            int departmentTotal,
            int departmentCreated,
            int departmentUpdated,
            int departmentDisabled,
            int userTotal,
            int userCreated,
            int userUpdated,
            int userDisabled,
            int conflictCount,
            List<String> conflicts) {}

    /** 组织同步执行日志视图。 */
    public record SyncLog(
            String id,
            String triggerType,
            String status,
            int departmentTotal,
            int departmentCreated,
            int departmentUpdated,
            int departmentDisabled,
            int userTotal,
            int userCreated,
            int userUpdated,
            int userDisabled,
            int conflictCount,
            String errorMessage,
            String startedBy,
            LocalDateTime startedAt,
            LocalDateTime endedAt) {}
}
