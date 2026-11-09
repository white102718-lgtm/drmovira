package com.adpulse.system.feedback.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;

/** 产品反馈接口请求契约。 */
public final class FeedbackRequests {
    private FeedbackRequests() {}

    /**
     * 提交反馈请求。
     *
     * @param category 反馈类型：FEATURE、BUG、EXPERIENCE
     * @param title 反馈标题
     * @param content 反馈完整描述
     * @param attachmentFileIds 当前用户已上传的通用文件ID，最多5个
     * @param diagnostics 经前端脱敏并限制数量的客户端诊断快照
     */
    public record Create(
            @NotBlank(message = "请选择反馈类型") String category,
            @NotBlank(message = "请填写反馈标题") @Size(max = 100, message = "反馈标题不能超过100个字") String title,
            @NotBlank(message = "请填写反馈内容") @Size(max = 5000, message = "反馈内容不能超过5000个字") String content,
            @Size(max = 5, message = "最多上传5个附件") List<Long> attachmentFileIds,
            @Valid Diagnostics diagnostics) {}

    /** 客户端运行环境快照；服务端只接受分析所需的有限字段。 */
    public record Diagnostics(
            @Size(max = 64) String appVersion,
            @Size(max = 1000) String pageUrl,
            @Size(max = 200) String routeName,
            @Size(max = 32) String language,
            @Size(max = 64) String timezone,
            @Size(max = 20) String deviceType,
            @Size(max = 100) String operatingSystem,
            @Size(max = 100) String browser,
            @Size(max = 32) String screenResolution,
            @Size(max = 32) String viewportSize,
            Double devicePixelRatio,
            Integer hardwareConcurrency,
            Double deviceMemory,
            @Size(max = 64) String networkType,
            @Size(max = 100) List<@Valid ConsoleEntry> consoleLogs) {}

    /** 已脱敏的前端控制台条目。 */
    public record ConsoleEntry(
            @Pattern(regexp = "log|info|warn|error", message = "控制台日志级别不正确") String level,
            @Size(max = 40) String timestamp,
            @Size(max = 2000) String message) {}

    /** 管理端更新反馈跟进信息；负责人为空时表示暂未分配。 */
    public record UpdateStatus(
            @NotBlank(message = "请选择处理状态") String status,
            @Positive(message = "负责人ID不正确") Long ownerId,
            @Size(max = 5000, message = "处理说明不能超过5000个字") String adminReply) {}
}
