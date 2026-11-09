package com.adpulse.main.cardstation.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Data;

/** 卡台管理持久化模型。 */
public final class CardStationModels {
    private CardStationModels() {}

    /** 卡片持久化模型。 */
    @Data
    public static class Card {
        private Long id;
        private String platform;
        private String externalCardId;
        private String cardName;
        private String maskedPan;
        private String cardStatus;
        private BigDecimal balance;
        private String currency;
        private String advertisementAccountId;
        private String companyEntity;
        private BigDecimal dailyLimit;
        private BigDecimal monthlyLimit;
        private BigDecimal transactionMinAmount;
        private BigDecimal transactionMaxAmount;
        private BigDecimal utilizationLimitAmount;
        private String utilizationLimitPreset;
        private BigDecimal periodMaxConsumeAmount;
        private LocalDateTime providerCreatedAt;
        private LocalDateTime providerUpdatedAt;
        private LocalDateTime createdAt;
        private LocalDateTime updatedAt;
    }

    /** 卡台余额持久化模型。 */
    @Data
    public static class Balance {
        private String productCode;
        private String currency;
        private BigDecimal balance;
        private BigDecimal frozenBalance;
    }

    /** 卡片统计持久化模型。 */
    @Data
    public static class Statistics {
        private Long total;
        private Long active;
        private Long frozen;
        private BigDecimal balance;
    }

    /** 限额调整记录持久化模型。 */
    @Data
    public static class LimitRecord {
        private Long id;
        private String externalCardId;
        private BigDecimal oldAmount;
        private BigDecimal newAmount;
        private String preset;
        private Integer status;
        private String errorMessage;
        private LocalDateTime createdAt;
    }

    /** 卡日授权额度规则持久化模型。 */
    @Data
    public static class LimitRule {
        private Long id;
        private Integer dailyPeriod;
        private BigDecimal adjustAmount;
        private BigDecimal minAmount;
        private Boolean autoAdjustEnabled;
        private Long updatedBy;
        private LocalDateTime createdAt;
        private LocalDateTime updatedAt;
    }
}
