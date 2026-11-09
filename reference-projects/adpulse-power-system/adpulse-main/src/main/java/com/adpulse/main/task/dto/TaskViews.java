package com.adpulse.main.task.dto;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

/** 任务中心响应模型。 */
public final class TaskViews {
    private TaskViews() {}

    /** 公共任务视图。 */
    public record Task(
            String id,
            String taskCode,
            String taskType,
            String projectId,
            String projectName,
            String title,
            String description,
            String creatorId,
            String creatorName,
            String ownerId,
            String ownerName,
            String assignerId,
            String assignerName,
            LocalDateTime assignedAt,
            String priority,
            String status,
            LocalDateTime dueAt,
            LocalDateTime acceptedAt,
            LocalDateTime completedAt,
            LocalDateTime withdrawnAt,
            String withdrawReason,
            LocalDateTime rejectedAt,
            String rejectedBy,
            String rejectionReason,
            int version,
            LocalDateTime createdAt,
            LocalDateTime updatedAt,
            boolean followed,
            boolean deliveryOperator,
            String amNames) {}

    /** 任务草稿视图。 */
    public record Draft(
            String id,
            String draftCode,
            String taskType,
            String creatorId,
            String creatorName,
            String title,
            String projectId,
            JsonNode payload,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {}

    /** 与当前用户关联的任务历史动态。 */
    public record Activity(
            String id,
            String taskId,
            String taskType,
            String projectId,
            String taskTitle,
            String eventType,
            String state,
            String actorId,
            String actorName,
            String description,
            LocalDateTime occurredAt) {}

    /** 任务中心左侧导航数量。 */
    public record NavigationCounts(
            long owned,
            long assigned,
            long followed,
            long activities,
            long drafts,
            long all,
            long created,
            long submission,
            long acceptance,
            long completed,
            long failed) {}

    public record Delivery(
            String productUrl,
            String region,
            String target,
            LocalDateTime plannedStartAt,
            String amUserId,
            String amUserName,
            List<UserAssignment> amUsers,
            List<TaskRequests.DeliveryItem> items) {}

    /** 新建投放任务使用的代理线主数据；选择后复制为任务快照。 */
    public record AgencyLineOption(
            String id,
            String name,
            String type,
            String pixelName,
            String pixelId,
            @JsonIgnore String tokenCiphertext,
            String token,
            String testCode,
            String deliveryUrl,
            String optimizerId,
            String optimizerName,
            String cloakUrl) {
        /** 兼容只关心代理线标识与名称的内部校验及既有测试。 */
        public AgencyLineOption(String id, String name) {
            this(id, name, "", "", "", null, "", "", "", "", "", "");
        }

        @Override
        public String toString() {
            return "AgencyLineOption[redacted]";
        }
    }

    /** 任务中的用户快照。 */
    public record UserAssignment(String userId, String userName) {}

    /** 团队与线路分配。 */
    public record Allocation(
            String id,
            String teamCode,
            String teamName,
            String teamOwnerId,
            String teamOwnerName,
            int pwaLineCount,
            int h5LineCount,
            int sortOrder,
            String status,
            LocalDateTime submittedAt,
            LocalDateTime completedAt) {}

    /** 素材任务详情。 */
    public record Material(
            String demandType,
            String languageCode,
            boolean greenMaterial,
            String departmentId,
            String departmentName,
            String productSubName,
            int quantity,
            boolean addToLibrary,
            List<String> countryTags,
            List<String> themeTags,
            List<String> gameplayTags) {}

    /** 素材需求描述视图。 */
    public record MaterialRequirement(
            String id,
            int sortOrder,
            String description,
            String duration,
            int quantity,
            String link,
            String remark,
            String compliance) {}

    /** 投放交付视图。 */
    public record DeliverySubmission(
            String id,
            String allocationId,
            int versionNo,
            String requestId,
            String submittedBy,
            String submittedByName,
            String platform,
            List<String> platforms,
            String adAccountId,
            List<String> adAccountIds,
            int accountCount,
            String adAccountName,
            LocalDateTime actualStartAt,
            BigDecimal actualBudget,
            BigDecimal actualSpend,
            BigDecimal dailyReportSpend,
            String currency,
            int campaignCount,
            int adsetCount,
            int adCount,
            String deliveryStatus,
            String exceptionNote,
            String submissionNote,
            LocalDateTime submittedAt,
            String reviewStatus,
            String reviewerId,
            String reviewerName,
            String reviewComment,
            LocalDateTime reviewedAt,
            List<DeliveryObject> objects) {}

    /** 投放交付关联的广告对象。 */
    public record DeliveryObject(
            String objectType, String objectId, String objectName, int sortOrder) {}

    /** 投手当前任务明细对应的交付数据源汇总。 */
    public record DeliverySource(
            LocalDate startDate,
            LocalDate endDate,
            List<String> platforms,
            List<String> accountIds,
            List<String> campaignIds,
            List<String> adsetIds,
            List<String> adIds,
            BigDecimal actualSpend,
            BigDecimal dailyReportSpend) {}

    /** 素材交付视图。 */
    public record MaterialSubmission(
            String id,
            int versionNo,
            String requestId,
            String submittedBy,
            String submittedByName,
            int deliveredQuantity,
            String submissionNote,
            LocalDateTime submittedAt,
            String reviewStatus,
            String reviewerId,
            String reviewerName,
            String reviewComment,
            LocalDateTime reviewedAt,
            String libraryStatus) {}

    /** 任务详情及其类型化数据。 */
    public record Detail(
            Task task,
            Delivery delivery,
            List<String> platforms,
            List<Allocation> allocations,
            Material material,
            List<String> sizes,
            List<MaterialRequirement> materialRequirements,
            List<ReferenceLink> referenceLinks,
            List<FileView> taskFiles,
            List<DeliverySubmission> deliverySubmissions,
            List<MaterialSubmission> materialSubmissions) {}

    /** 外部参考链接。 */
    public record ReferenceLink(String name, String url, int sortOrder) {}

    /** 任务文件视图。 */
    public record FileView(
            String id,
            String originalName,
            String extension,
            long fileSize,
            String mimeType,
            String targetType,
            String targetId,
            String usageType,
            int sortOrder) {}

    /** 分页响应。 */
    public record Page<T>(List<T> items, long total, int page, int pageSize) {}

    /** 来源投放任务关联的 MongoDB 素材任务摘要，工单 ID 用于打开素材详情。 */
    public record RelatedMaterialTask(
            String id,
            String taskCode,
            String orderNo,
            String title,
            String status,
            String ownerName,
            String requesterName,
            Integer quantity,
            Integer completedQuantity,
            java.time.Instant createdAt,
            java.time.Instant expectedDeliveryAt) {}
}
