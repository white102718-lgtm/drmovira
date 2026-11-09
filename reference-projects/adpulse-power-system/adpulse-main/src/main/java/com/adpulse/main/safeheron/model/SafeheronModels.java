package com.adpulse.main.safeheron.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Data;

/** Safeheron归集管理持久化模型。 */
public final class SafeheronModels {
    private SafeheronModels() {}

    /** 归集规则持久化模型。 */
    @Data
    public static class Rule {
        private Long id;
        private Long departmentId;
        private String departmentName;
        private String collectAccountKey;
        private String collectAccountName;
        private String coinKey;
        private BigDecimal thresholdUsd;
        private Integer frequency;
        private Integer gasStationEnabled;
        private BigDecimal reserveGas;
        private BigDecimal maxTxFee;
        private String signer;
        private Integer status;
        private Integer effectiveStatus;
        private Long createdBy;
        private Long updatedBy;
        private LocalDateTime createdAt;
        private LocalDateTime updatedAt;
    }

    /** 钱包持久化模型。 */
    @Data
    public static class Wallet {
        private Long id;
        private String accountKey;
        private String accountName;
        private String customerRefId;
        private String teamId;
    }

    /** 钱包币种持久化模型。 */
    @Data
    public static class Coin {
        private String accountKey;
        private String coinKey;
        private String coinName;
        private String feeUnit;
        private String addressCiphertext;
    }

    /** 团队审批配置持久化模型。 */
    @Data
    public static class Team {
        private String teamId;
        private String teamName;
        private Long approverId;
        private String approverName;
        private Integer status;
        private String baseUrl;
        private String apiKey;
        private String privateKeyCiphertext;
        private String safeheronPublicKey;
        private Long requestTimeout;
        private Long createdBy;
        private Long updatedBy;
    }

    /** 系统用户选项持久化模型。 */
    @Data
    public static class User {
        private Long userId;
        private String userName;
        private String nickName;
    }

    /** 部门持久化模型。 */
    @Data
    public static class Department {
        private Long id;
        private Long parentId;
        private String label;
    }

    /** 归集记录持久化模型。 */
    @Data
    public static class CollectionRecord {
        private Long id;
        private String teamId;
        private Long departmentId;
        private String departmentName;
        private String taskId;
        private String sourceAccountName;
        private String destAccountName;
        private String coinKey;
        private String coinName;
        private BigDecimal amount;
        private BigDecimal amountUsd;
        private BigDecimal gasFee;
        private Integer status;
        private String transactionType;
        private Long approverId;
        private String approverName;
        private Integer approveResult;
        private String txHash;
        private String remark;
        private LocalDateTime createdAt;
    }

    /** 归集记录聚合模型。 */
    @Data
    public static class RecordAggregate {
        private Long totalCount;
        private Long successCount;
        private BigDecimal amountUsd;
        private BigDecimal gasFee;
    }
}
