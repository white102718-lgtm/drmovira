package com.adpulse.main.adaccountasset;

import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Data;

/** 广告账户台账模块的持久化模型。 */
public final class AdAccountAssetModels {
    private AdAccountAssetModels() {}

    /** 广告账户资产信息主表模型；存在记录时不再回退到飞书历史数据。 */
    @Data
    public static class AdAccountAsset {
        private Long id;
        private String accountId;
        private String accountName;
        private Integer accountStatus;
        private String inventoryStatus;
        private String accountType;
        private String accountAttribute;
        private Long channelId;
        private String channelName;
        private String managedBm;
        private String managedBmId;
        private String backupManagedBm;
        private String backupManagedBmId;
        private String timezone;
        private String cardStation;
        private String cardNumber;
        private String remark;
        private LocalDate deliveryDate;
        private Boolean isManuallyUpdated;
        private LocalDateTime manuallyUpdatedAt;
        private Long manuallyUpdatedBy;
        private LocalDateTime lastMongoSyncAt;
        private LocalDateTime lastFeishuSyncAt;
        private String updateSource;
        private Long createdBy;
        private Long updatedBy;
        private LocalDateTime createdAt;
        private LocalDateTime updatedAt;
    }

    /** 广告账户与使用人的多对多分配关系。 */
    @Data
    public static class AdAccountAssetAssignment {
        private Long id;
        private Long adAccountAssetId;
        private Long userId;
        private String userName;
        private String usageTeamName;
        private Boolean isPrimary;
        private String assignmentStatus;
        private String assignmentSource;
        private Long applicationId;
        private LocalDateTime assignedAt;
        private LocalDateTime releasedAt;
        private Long createdBy;
        private Long updatedBy;
        private LocalDateTime createdAt;
        private LocalDateTime updatedAt;
    }

    /** 广告账户列表批量查询使用人的当前主部门，避免逐个用户回查组织信息。 */
    @Data
    public static class UserDepartment {
        private Long userId;
        private String departmentName;
    }

    /** Excel 导入按显示名称解析使用人时使用的有效用户快照。 */
    @Data
    public static class ActiveUser {
        private String departmentName;
        private Long userId;
        private String displayName;
    }

    /** 账户属性配置模型。 */
    @Data
    public static class AccountAttribute {
        private Long id;
        private String accountAttribute;
        private Long createdBy;
        private LocalDateTime createdAt;
        private LocalDateTime updatedAt;
    }

    /** 广告账户资料变更事件；差异 JSON 只保存展示快照，不保存任何授权凭据。 */
    @Data
    public static class AdAccountAssetChangeEvent {
        private Long id;
        private Long adAccountAssetId;
        private String accountId;
        private String eventType;
        private String updateSource;
        private Long actorId;
        private String actorName;
        private String changesJson;
        private LocalDateTime occurredAt;
    }
}
