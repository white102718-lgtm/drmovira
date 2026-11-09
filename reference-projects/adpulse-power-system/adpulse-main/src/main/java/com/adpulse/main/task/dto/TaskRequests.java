package com.adpulse.main.task.dto;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/** 任务中心写入请求。 */
public final class TaskRequests {
    private TaskRequests() {}

    /** 公共任务创建字段。 */
    public record BaseCreate(
            @NotBlank @Size(max = 200) String title,
            @Size(max = 5000) String description,
            @NotBlank String projectId,
            String ownerId,
            @NotBlank @Size(max = 10) String priority,
            LocalDateTime dueAt) {}

    /** 投放任务创建请求。 */
    public record DeliveryCreate(
            @NotNull @Valid BaseCreate task,
            @NotNull @Size(max = 1000) String productUrl,
            @NotBlank @Size(max = 100) String region,
            @NotBlank @Size(max = 1000) String target,
            @NotNull LocalDateTime plannedStartAt,
            @NotEmpty List<@NotBlank @Size(max = 100) String> platforms,
            List<@Valid FileBinding> files,
            String draftId,
            @NotEmpty @Size(max = 1000) List<@NotNull @Valid DeliveryItem> items) {}

    /** AM 指定给投手的投放明细；交付按投手汇总，不关联单条明细。 */
    public record DeliveryItem(
            @Size(max = 50) String type,
            @NotBlank @Size(max = 100) String platform,
            @Size(max = 200) String pixelName,
            @NotBlank @Size(max = 100) String pixelId,
            @NotBlank @Size(max = 10000) String token,
            @NotBlank @Size(max = 200) String testCode,
            @Size(max = 200) String channelName,
            @NotBlank @Size(max = 2000) String deliveryUrl,
            @NotBlank String operatorId,
            @Size(max = 2000) String cloakUrl,
            String channelId,
            String agencyLineId,
            @NotBlank @Size(max = 80) String agencyLineName) {
        /** 兼容未携带行级投放平台的历史内部调用。 */
        public DeliveryItem(
                String type,
                String pixelName,
                String pixelId,
                String token,
                String testCode,
                String channelName,
                String deliveryUrl,
                String operatorId,
                String cloakUrl,
                String channelId,
                String agencyLineId,
                String agencyLineName) {
            this(
                    type,
                    "facebook",
                    pixelName,
                    pixelId,
                    token,
                    testCode,
                    channelName,
                    deliveryUrl,
                    operatorId,
                    cloakUrl,
                    channelId,
                    agencyLineId,
                    agencyLineName);
        }

        @Override
        public String toString() {
            return "DeliveryItem[redacted]";
        }
    }

    /** 导入代理线名称批量匹配，不接受空名称或无限量查询。 */
    public record AgencyLineMatch(
            @NotEmpty @Size(max = 1000) List<@NotBlank @Size(max = 200) String> names) {}

    /** 团队线路分配。 */
    public record Allocation(
            // 沿用接口字段名，新建和重新提交时传组织架构部门 ID。
            @NotBlank @Size(max = 30) String teamCode,
            @NotBlank String teamOwnerId,
            @Min(0) int pwaLineCount,
            @Min(0) int h5LineCount) {}

    /** 投放负责人为投手建立的团队执行项。 */
    public record DeliveryAllocationAssign(@NotEmpty List<@Valid Allocation> allocations) {}

    /** 素材任务创建请求。 */
    public record MaterialCreate(
            @NotNull @Valid BaseCreate task,
            @NotBlank @Size(max = 50) String demandType,
            @NotBlank @Size(max = 100) String languageCode,
            @NotNull Boolean greenMaterial,
            @Size(max = 200) String productSubName,
            @NotEmpty List<@NotBlank @Size(max = 100) String> sizes,
            List<@Size(max = 100) String> countryTags,
            List<@Size(max = 100) String> themeTags,
            List<@Size(max = 100) String> gameplayTags,
            @NotEmpty List<@Valid MaterialRequirement> requirements,
            List<@Valid FileBinding> referenceFiles,
            String draftId) {}

    /** 新建或更新任务草稿请求。 */
    public record DraftSave(
            @NotBlank @Size(max = 20) String taskType,
            @Size(max = 200) String title,
            String projectId,
            @NotNull JsonNode payload) {}

    public record MaterialRequirement(
            @NotBlank @Size(max = 2000) String description,
            @Size(max = 50) String duration,
            @Min(1) int quantity,
            @Size(max = 2000) String link,
            @Size(max = 2000) String remark,
            @Size(max = 2000) String compliance,
            List<@Valid FileBinding> files) {}

    /** 任务负责人分配请求。 */
    public record Assign(@NotBlank String ownerId) {}

    /** 素材任务外部参考链接。 */
    public record ReferenceLink(
            @NotBlank @Size(max = 255) String name, @NotBlank @Size(max = 2000) String url) {}

    /** 文件引用。 */
    public record FileBinding(
            @NotBlank String fileId,
            @NotBlank @Size(max = 30) String usageType,
            @Min(0) int sortOrder) {}

    /** 投放交付请求。 */
    public record DeliverySubmissionCreate(
            @NotBlank @Size(max = 64) String requestId,
            @NotEmpty @Size(max = 20) List<@NotBlank @Size(max = 100) String> platforms,
            @NotEmpty @Size(max = 100) List<@NotBlank @Size(max = 100) String> accountIds,
            @Size(max = 255) String adAccountName,
            @NotNull LocalDateTime actualStartAt,
            @NotNull @DecimalMin(value = "0", inclusive = false) BigDecimal actualBudget,
            @NotNull @DecimalMin("0") BigDecimal actualSpend,
            @NotNull @DecimalMin("0") BigDecimal dailyReportSpend,
            @NotBlank @Size(min = 3, max = 3) String currency,
            @Min(1) int campaignCount,
            @Min(0) int adsetCount,
            @Min(0) int adCount,
            @NotBlank String deliveryStatus,
            @Size(max = 1000) String exceptionNote,
            @Size(max = 5000) String note,
            @NotEmpty List<@Valid DeliveryObject> objects,
            List<@Valid FileBinding> files) {}

    /** 投放交付关联广告对象。 */
    public record DeliveryObject(
            @NotBlank String objectType,
            @NotBlank @Size(max = 200) String objectId,
            @Size(max = 255) String objectName) {}

    /** 素材交付请求。 */
    public record MaterialSubmissionCreate(
            @NotBlank @Size(max = 64) String requestId,
            @Min(1) int deliveredQuantity,
            @Size(max = 5000) String note,
            @NotEmpty List<@Valid FileBinding> files) {}

    /** 验收请求。 */
    public record Review(@Size(max = 1000) String comment) {}

    /** 撤回请求。 */
    public record Withdraw(@NotBlank @Size(max = 500) String reason) {}

    /** 负责人驳回接收任务请求。 */
    public record Decline(@NotBlank @Size(max = 500) String reason) {}
}
