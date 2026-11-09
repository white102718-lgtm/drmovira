package com.adpulse.system.feedback.dto;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.LocalDateTime;
import java.util.List;

/** 产品反馈查询响应契约，所有大整数ID均以字符串返回。 */
public final class FeedbackViews {
    private FeedbackViews() {}

    /** 管理列表使用的轻量反馈摘要。 */
    public record ListItem(
            String id,
            String category,
            String title,
            String content,
            String status,
            String submittedByName,
            String submittedByUsername,
            String clientIp,
            String deviceType,
            String ownerId,
            String ownerName,
            int attachmentCount,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {}

    /** 管理列表顶部展示的反馈状态汇总。 */
    public record Summary(long total, long pending, long processing, long resolved, long closed) {}

    /** 反馈附件下载信息。 */
    public record Attachment(
            String id, String originalName, String mimeType, Long fileSize, Integer sortOrder) {}

    /** 管理端反馈详情，包含诊断快照和附件。 */
    public record Detail(
            String id,
            String category,
            String title,
            String content,
            String status,
            String submittedById,
            String submittedByName,
            String submittedByUsername,
            String clientIp,
            String userAgent,
            String deviceType,
            String pageUrl,
            JsonNode diagnostics,
            String adminReply,
            String ownerId,
            String ownerName,
            String processedById,
            String processedByName,
            LocalDateTime processedAt,
            List<Attachment> attachments,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {}
}
