package com.adpulse.main.task.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Data;

/** 任务领域持久化模型集合。 */
public final class TaskModels {
    private TaskModels() {}

    /** 公共任务。 */
    @Data
    public static class Task {
        private Long id;
        private String taskCode;
        private String taskType;
        private Long projectId;
        private String projectName;

        /** 投放任务关联 AM 的姓名，按任务分配顺序展示。 */
        private String amNames;

        private String title;
        private String description;
        private Long creatorId;
        private String creatorName;
        private Long ownerId;
        private String ownerName;
        private Long assignerId;
        private String assignerName;
        private LocalDateTime assignedAt;
        private String priority;
        private String status;
        private LocalDateTime dueAt;
        private LocalDateTime acceptedAt;
        private LocalDateTime completedAt;
        private LocalDateTime withdrawnAt;
        private String withdrawReason;
        private LocalDateTime rejectedAt;
        private Long rejectedBy;
        private String rejectionReason;
        private Integer version;
        private Long createdBy;
        private Long updatedBy;
        private LocalDateTime createdAt;
        private LocalDateTime updatedAt;
        private Boolean followed;
        private Boolean deliveryOperator;
    }

    /** 任务表单草稿。 */
    @Data
    public static class Draft {
        private Long id;
        private String draftCode;
        private String taskType;
        private Long creatorId;
        private String creatorName;
        private String title;
        private Long projectId;
        private String payloadJson;
        private Long createdBy;
        private Long updatedBy;
        private LocalDateTime createdAt;
        private LocalDateTime updatedAt;
    }

    /** 任务历史动态。 */
    @Data
    public static class Activity {
        private Long id;
        private Long taskId;
        private String taskType;
        private Long projectId;
        private String taskTitle;
        private String eventType;
        private String state;
        private Long actorId;
        private String actorName;
        private String description;
        private LocalDateTime createdAt;
    }

    /** 投放任务详情。 */
    @Data
    public static class DeliveryDetail {
        private Long id;
        private Long taskId;
        private String productUrl;
        private String itemsCiphertext;
        private String regionValue;
        private String targetDescription;
        private LocalDateTime plannedStartAt;
        private Long amUserId;
        private String amUserName;
    }

    /** 投放任务团队线路分配。 */
    @Data
    public static class Allocation {
        private Long id;
        private Long taskId;
        private String teamCode;
        private String teamName;
        private Long teamOwnerId;
        private String teamOwnerName;
        private Integer pwaLineCount;
        private Integer h5LineCount;
        private Integer sortOrder;
        private String status;
        private LocalDateTime submittedAt;
        private LocalDateTime completedAt;
    }

    /** 素材任务详情。 */
    @Data
    public static class MaterialDetail {
        private Long id;
        private Long taskId;
        private String demandType;
        private String languageCode;
        private Boolean greenMaterial;
        private Long departmentId;
        private String departmentName;
        private String productSubName;
        private Integer quantity;
        private Boolean addToLibrary;
        private String countryTags;
        private String themeTags;
        private String gameplayTags;
    }

    /** 素材任务需求描述。 */
    @Data
    public static class MaterialRequirement {
        private Long id;
        private Long taskId;
        private Integer sortOrder;
        private String description;
        private String durationText;
        private Integer quantity;
        private String relatedLink;
        private String remark;
        private String complianceRequirement;
        private Long createdBy;
        private Long updatedBy;
    }

    /** 用户主部门快照。 */
    @Data
    public static class DepartmentSnapshot {
        private Long id;
        private String name;
    }

    /** 创建投放任务时需要快照的项目 AM 与投放负责人。 */
    @Data
    public static class ProjectTaskOwners {
        private Long amUserId;
        private String amUserName;
        private Long deliveryLeaderId;
        private String deliveryLeaderName;
    }

    /** 项目或投放任务的 AM 用户快照。 */
    @Data
    public static class UserSnapshot {
        private Long userId;
        private String userName;
        private Integer sortOrder;
    }

    /** 投放任务交付。 */
    @Data
    public static class DeliverySubmission {
        private Long id;
        private Long taskId;
        private Long allocationId;
        private Integer versionNo;
        private String requestId;
        private Long submittedBy;
        private String submittedByName;
        private String platformValue;
        private String adAccountId;
        private String adAccountName;
        private LocalDateTime actualStartAt;
        private BigDecimal actualBudget;
        private BigDecimal actualSpend;
        private BigDecimal dailyReportSpend;
        private String currency;
        private Integer campaignCount;
        private Integer adsetCount;
        private Integer adCount;
        private String deliveryStatus;
        private String exceptionNote;
        private String submissionNote;
        private LocalDateTime submittedAt;
        private String reviewStatus;
        private Long reviewerId;
        private String reviewerName;
        private String reviewComment;
        private LocalDateTime reviewedAt;
    }

    /** 素材任务交付。 */
    @Data
    public static class MaterialSubmission {
        private Long id;
        private Long taskId;
        private Integer versionNo;
        private String requestId;
        private Long submittedBy;
        private String submittedByName;
        private Integer deliveredQuantity;
        private String submissionNote;
        private LocalDateTime submittedAt;
        private String reviewStatus;
        private Long reviewerId;
        private String reviewerName;
        private String reviewComment;
        private LocalDateTime reviewedAt;
        private String libraryStatus;
    }
}
