package com.adpulse.system.feedback.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 产品反馈持久化模型，保存提交身份、来源环境和处理状态快照。 */
@Data
public class Feedback {
    private Long id;
    private String category;
    private String title;
    private String content;
    private String status;
    private Long submittedById;
    private String submittedByName;
    private String submittedByUsername;
    private String clientIp;
    private String userAgent;
    private String deviceType;
    private String pageUrl;
    private String diagnosticJson;
    private String adminReply;
    private Long ownerId;
    private String ownerName;
    private Long processedById;
    private String processedByName;
    private LocalDateTime processedAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    private Integer attachmentCount;
}
