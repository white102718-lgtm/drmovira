package com.adpulse.main.adaccountasset;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;

/** 广告账户资产台账的保存和批量导入请求。 */
public final class AdAccountAssetRequests {
    private AdAccountAssetRequests() {}

    /** 广告账户分页筛选条件；文本字段包含匹配，下拉字段精确匹配。 */
    public record PageFilter(
            List<String> accountNames,
            List<String> accountIds,
            List<Integer> accountStatuses,
            List<String> accountTypes,
            List<String> accountAttributes,
            List<String> channelNames,
            List<String> managedBms,
            List<String> managedBmIds,
            List<String> backupManagedBms,
            List<String> backupManagedBmIds,
            List<String> timezones,
            List<String> cardStations,
            List<String> cardNumbers,
            List<String> inventoryStatuses,
            List<String> usageUsers,
            List<String> usageDepartments,
            List<String> inventoryAssigneeNames) {
        public static final PageFilter EMPTY =
                new PageFilter(
                        null, null, null, null, null, null, null, null, null, null, null, null,
                        null, null, null, null, null);
    }

    /** 按资产管理页筛选条件一次读取全部广告账户，用于导出和跨页批量处理。 */
    public record AccountSearch(@Size(max = 500) String keyword, @Valid PageFilter filter) {}

    public record Save(
            @Size(max = 255) String accountName,
            @Size(max = 100) String accountType,
            @Size(max = 100) String accountAttribute,
            @Size(max = 20) String channelId,
            @Size(max = 500) String managedBm,
            @Size(max = 100) String managedBmId,
            @Size(max = 500) String backupManagedBm,
            @Size(max = 100) String backupManagedBmId,
            @Size(max = 100) String timezone,
            @Size(max = 100) String cardStation,
            @Size(max = 100) String cardNumber,
            @Size(max = 500) String remark) {}

    /** 批量修改时由客户端显式声明要覆盖的字段；未声明的字段保持各账户原值。 */
    public enum BatchUpdateField {
        ACCOUNT_TYPE,
        ACCOUNT_ATTRIBUTE,
        CHANNEL_ID,
        MANAGED_BM,
        MANAGED_BM_ID,
        BACKUP_MANAGED_BM,
        BACKUP_MANAGED_BM_ID,
        TIMEZONE,
        CARD_STATION,
        CARD_NUMBER,
        REMARK,
        INVENTORY_STATUS,
        USAGE_USER_IDS
    }

    /** 广告账户台账批量字段覆盖请求；可选字段传空白值表示清空。 */
    public record BatchUpdate(
            @NotEmpty @Size(max = 100) List<@NotBlank @Size(max = 100) String> accountIds,
            @NotEmpty Set<@NotNull BatchUpdateField> changedFields,
            @Size(max = 100) String accountType,
            @Size(max = 100) String accountAttribute,
            @Size(max = 20) String channelId,
            @Size(max = 500) String managedBm,
            @Size(max = 100) String managedBmId,
            @Size(max = 500) String backupManagedBm,
            @Size(max = 100) String backupManagedBmId,
            @Size(max = 100) String timezone,
            @Size(max = 100) String cardStation,
            @Size(max = 100) String cardNumber,
            @Size(max = 500) String remark,
            @Size(max = 24) String inventoryStatus,
            @Size(max = 100) List<@NotNull Long> userIds) {}

    public record ImportItem(
            @NotNull Integer line,
            @NotBlank @Size(max = 100) String accountId,
            @Size(max = 255) String accountName,
            @Size(max = 100) String accountType,
            @Size(max = 100) String accountAttribute,
            @Size(max = 20) String channelId,
            @Size(max = 255) String channelName,
            @Size(max = 500) String managedBm,
            @Size(max = 100) String managedBmId,
            @Size(max = 500) String backupManagedBm,
            @Size(max = 100) String backupManagedBmId,
            @Size(max = 100) String timezone,
            @Size(max = 100) String cardStation,
            @Size(max = 100) String cardNumber,
            @Size(max = 500) String remark,
            @Size(max = 2000) String usageUsers) {
        Save toSave() {
            return new Save(
                    accountName,
                    accountType,
                    accountAttribute,
                    channelId,
                    managedBm,
                    managedBmId,
                    backupManagedBm,
                    backupManagedBmId,
                    timezone,
                    cardStation,
                    cardNumber,
                    remark);
        }
    }

    /** 账户属性配置保存请求。 */
    public record AccountAttributeSave(@NotBlank @Size(max = 15) String accountAttribute) {}

    public record ImportRequest(
            @NotNull @Size(min = 1, max = 5000) List<@NotNull ImportItem> items) {}

    /** 广告账户使用人分配请求；供人工分配和申请办理复用。 */
    public record AssignmentSave(
            @NotNull @Size(min = 1, max = 500) List<@NotBlank String> accountIds,
            @NotNull Long userId,
            @NotBlank @Size(max = 100) String userName,
            boolean primary,
            @NotBlank @Size(max = 30) String source,
            Long applicationId) {}

    /** 资产管理页面整体替换某个广告账户的当前使用人。 */
    public record AssignmentReplace(
            @NotNull @Size(max = 100) List<@NotNull Long> userIds,
            @NotBlank @Size(max = 30) String source,
            @NotBlank @Size(max = 24) String inventoryStatus) {}

    /** 按广告账户 ID 批量读取资产台账，用于其他业务页面复用统一展示口径。 */
    public record AccountBatchQuery(
            @NotNull @Size(min = 1, max = 1000) List<@NotBlank @Size(max = 100) String> accountIds) {}

    /** 电子表格中的一行保存；账户 ID 命中时更新，否则新增资产台账。 */
    public record SpreadsheetUpdateRow(
            @NotBlank @Size(max = 100) String accountId,
            @Size(max = 255) String accountName,
            @NotEmpty Set<@NotNull BatchUpdateField> changedFields,
            @Size(max = 100) String accountType,
            @Size(max = 100) String accountAttribute,
            @Size(max = 20) String channelId,
            @Size(max = 500) String managedBm,
            @Size(max = 100) String managedBmId,
            @Size(max = 500) String backupManagedBm,
            @Size(max = 100) String backupManagedBmId,
            @Size(max = 100) String timezone,
            @Size(max = 100) String cardStation,
            @Size(max = 100) String cardNumber,
            @Size(max = 500) String remark,
            @Size(max = 24) String inventoryStatus,
            @Size(max = 100) List<@NotNull Long> userIds) {
        BatchUpdate toSpreadsheetBatchUpdate() {
            List<Long> normalizedUserIds =
                    userIds == null ? List.of() : userIds.stream().distinct().toList();
            Set<BatchUpdateField> normalizedFields = EnumSet.noneOf(BatchUpdateField.class);
            normalizedFields.addAll(changedFields);
            normalizedFields.add(BatchUpdateField.INVENTORY_STATUS);
            if (normalizedUserIds.isEmpty()) {
                normalizedFields.remove(BatchUpdateField.USAGE_USER_IDS);
            } else {
                normalizedFields.add(BatchUpdateField.USAGE_USER_IDS);
            }
            return new BatchUpdate(
                    List.of(accountId),
                    normalizedFields,
                    accountType,
                    accountAttribute,
                    channelId,
                    managedBm,
                    managedBmId,
                    backupManagedBm,
                    backupManagedBmId,
                    timezone,
                    cardStation,
                    cardNumber,
                    remark,
                    normalizedUserIds.isEmpty() ? "AVAILABLE" : "ASSIGNED",
                    normalizedUserIds);
        }

        Save toSave() {
            return new Save(
                    accountName,
                    accountType,
                    accountAttribute,
                    channelId,
                    managedBm,
                    managedBmId,
                    backupManagedBm,
                    backupManagedBmId,
                    timezone,
                    cardStation,
                    cardNumber,
                    remark);
        }
    }

    public record SpreadsheetUpdate(
            @NotEmpty @Size(max = 1000) List<@NotNull @Valid SpreadsheetUpdateRow> rows) {}
}
