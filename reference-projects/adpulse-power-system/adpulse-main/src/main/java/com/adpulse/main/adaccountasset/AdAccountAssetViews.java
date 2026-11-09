package com.adpulse.main.adaccountasset;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

/** 广告账户清单与资产信息的接口返回结构。 */
public final class AdAccountAssetViews {
    private AdAccountAssetViews() {}

    public record Account(
            String accountId,
            String accountName,
            Integer accountStatus,
            BigDecimal accountDailyLimit,
            String inventoryStatus,
            String accountType,
            String accountAttribute,
            String managedBm,
            String managedBmId,
            String backupManagedBm,
            String backupManagedBmId,
            String timezone,
            String cardStation,
            String cardNumber,
            String remark,
            String usageUserId,
            String usageUserName,
            String usageDepartmentName,
            LocalDate deliveryDate,
            String channelId,
            String channelName,
            boolean manuallyUpdated,
            String syncStatus,
            LocalDateTime createdAt,
            List<Assignment> assignments) {}

    /** 广告账户当前有效使用人。 */
    public record Assignment(
            String id,
            String userId,
            String userName,
            boolean primary,
            String status,
            String source,
            String applicationId,
            LocalDateTime assignedAt) {}

    /** 账户属性配置视图。 */
    public record AccountAttribute(
            String id, String accountAttribute, java.time.LocalDateTime createTime) {}

    public record Page(List<Account> items, long total, int page, int pageSize) {}

    public record ImportFailure(int line, String accountId, String message) {}

    public record ImportResult(int totalCount, int successCount, List<ImportFailure> failures) {}

    /** 当前操作人的一条广告账户导入记录。 */
    public record ImportHistory(
            String id,
            String fileName,
            int totalCount,
            int successCount,
            List<ImportFailure> failures,
            LocalDateTime createdAt) {}

    /** 可下载的广告账户导入失败工作簿。 */
    public record ImportFailedFile(String contentBase64, String fileName) {}

    /** 广告账户电子表格新增与更新结果。 */
    public record SpreadsheetSaveResult(int createdCount, int updatedCount, List<Account> items) {}

    /** 广告账户生命周期中的一次使用区间。 */
    public record UsagePeriod(
            String userId,
            String userName,
            String teamName,
            java.time.LocalDateTime startedAt,
            java.time.LocalDateTime endedAt,
            String status,
            String applicationId,
            String source) {}

    /** 广告账户生命周期的脱敏事件。 */
    public record LifecycleEvent(
            String id,
            String eventType,
            String status,
            String actorName,
            String targetUserName,
            String teamName,
            String applicationId,
            java.time.LocalDateTime occurredAt,
            String description,
            String extraData,
            String source,
            String updateSource,
            List<LifecycleFieldChange> changes) {
        public LifecycleEvent(
                String id,
                String eventType,
                String status,
                String actorName,
                String targetUserName,
                String teamName,
                String applicationId,
                java.time.LocalDateTime occurredAt,
                String description,
                String extraData,
                String source) {
            this(
                    id,
                    eventType,
                    status,
                    actorName,
                    targetUserName,
                    teamName,
                    applicationId,
                    occurredAt,
                    description,
                    extraData,
                    source,
                    null,
                    List.of());
        }

        public LifecycleEvent(
                String id,
                String eventType,
                String status,
                String actorName,
                String targetUserName,
                String teamName,
                String applicationId,
                java.time.LocalDateTime occurredAt) {
            this(
                    id,
                    eventType,
                    status,
                    actorName,
                    targetUserName,
                    teamName,
                    applicationId,
                    occurredAt,
                    null,
                    null,
                    null,
                    null,
                    List.of());
        }
    }

    /** 选项值在变更当时的稳定 ID 与显示名称快照。 */
    public record LifecycleValueReference(String id, String name) {}

    /** 生命周期变更值；普通值使用 display，选项值额外携带 references。 */
    public record LifecycleChangeValue(
            String display, List<LifecycleValueReference> references, boolean redacted) {}

    /** 一次资料更新中的单字段实际差异。 */
    public record LifecycleFieldChange(
            String fieldKey,
            String fieldLabel,
            LifecycleChangeValue before,
            LifecycleChangeValue after) {}

    /** 广告账户服务自身可确认的生命周期详情；申请审批事件由 system 服务并行提供。 */
    public record LifecycleDetail(
            Account account, List<UsagePeriod> usagePeriods, List<LifecycleEvent> events) {}

    /** Facebook 广告账户的一条平台操作记录；不包含用于请求 Meta 的个号凭证。 */
    public record FacebookActivity(
            String id,
            String actorId,
            String actorName,
            String applicationId,
            String applicationName,
            String occurredAt,
            String localOccurredAt,
            String eventType,
            String translatedEventType,
            String objectId,
            String objectName,
            String objectType,
            String tool,
            String category,
            List<FacebookActivitySummaryItem> summaryItems,
            String extraData) {}

    /** Facebook 操作中可直接展示的一项变更或属性摘要。 */
    public record FacebookActivitySummaryItem(
            String label, String before, String after, String value) {}

    /** Facebook 操作记录的游标分页结果；until 在后续翻页中保持不变。 */
    public record FacebookActivityPage(
            List<FacebookActivity> items,
            String nextAfter,
            boolean hasMore,
            long since,
            long until) {}

    /** 广告账户的一次日限额变化；金额使用账户事件记录时的币种。 */
    public record DailyLimitChange(
            String id,
            BigDecimal previousLimit,
            BigDecimal currentLimit,
            String changeType,
            LocalDateTime changedAt,
            String source) {}

    /** 广告账户日限额变化记录分页结果。 */
    public record DailyLimitChangePage(
            String accountId,
            String accountName,
            String currency,
            BigDecimal currentLimit,
            LocalDateTime lastSyncedAt,
            List<DailyLimitChange> items,
            long total,
            int page,
            int pageSize) {}
}
