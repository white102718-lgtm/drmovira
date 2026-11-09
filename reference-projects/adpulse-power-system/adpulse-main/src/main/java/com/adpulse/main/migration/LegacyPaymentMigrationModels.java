package com.adpulse.main.migration;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Data;

/** 旧系统打款申请迁移使用的来源快照和目标写入模型。 */
public final class LegacyPaymentMigrationModels {
    private LegacyPaymentMigrationModels() {}

    public record LegacyPayment(
            Long sourceId,
            String orderNo,
            Long requesterSourceId,
            String requesterName,
            String requesterPhone,
            Long requesterTenantId,
            String sourceDepartmentName,
            Long sourceChannelId,
            String sourceChannelName,
            String paymentAddress,
            BigDecimal channelYesterdayCost,
            BigDecimal amount,
            String remark,
            String comment,
            Integer auditStatus,
            Integer sourceType,
            String feishuCardId,
            Integer feishuNoticeStatus,
            Long auditorSourceId,
            String auditorName,
            String auditorPhone,
            Long auditorTenantId,
            LocalDateTime auditTime,
            String rejectReason,
            BigDecimal actualAmount,
            String receiptUrl,
            Integer hasReceipt,
            String createBy,
            LocalDateTime createdAt,
            String updateBy,
            LocalDateTime updatedAt) {}

    public record TargetUser(
            Long id,
            String username,
            String displayName,
            String realName,
            String phone,
            Integer status,
            Long departmentId,
            String departmentName) {
        public String snapshotName() {
            if (displayName != null && !displayName.isBlank()) return displayName;
            if (realName != null && !realName.isBlank()) return realName;
            return username;
        }
    }

    public record TargetChannel(Long id, String channelName) {}

    public record PaymentDefinition(
            Long definitionId,
            String applicationName,
            Long configId,
            String formSchema,
            String nodes,
            Long configuredApproverId,
            String configuredApproverName) {}

    public record Ledger(Long sourcePaymentId, Long targetApplicationId, String sourceHash) {}

    public record ExistingApplication(Long id, String applicationNo) {}

    /** 已完成全部校验、可在一个目标事务中写入的申请。 */
    @Data
    public static class Candidate {
        private Long targetApplicationId;
        private LegacyPayment source;
        private TargetUser requester;
        private TargetUser auditor;
        private String requesterName;
        private String auditorName;
        private TargetChannel channel;
        private PaymentDefinition definition;
        private String applicationNo;
        private String targetStatus;
        private String sourceHash;
        private String formData;
        private String completionData;
        private int currentNodeIndex;
        private String approvalNodeName;
        private String handlerNodeName;
    }
}
