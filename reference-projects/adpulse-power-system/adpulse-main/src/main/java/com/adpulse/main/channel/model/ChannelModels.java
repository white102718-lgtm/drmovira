package com.adpulse.main.channel.model;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Data;

/** 渠道管理持久化模型集合。 */
public final class ChannelModels {
    private ChannelModels() {}

    /** 渠道及列表聚合模型。 */
    @Data
    public static class Channel {
        private Long id;
        private String channelName;
        private String channelShortName;
        private String channelCode;
        private Integer channelType;
        private String belongTeam;
        private Integer status;
        private Integer putawayStatus;
        private String settlementMethod;
        private String settlementCurrency;
        private BigDecimal buyoutAmount;
        private BigDecimal rechargeAmount;
        private String paymentAddress;
        private String loginUrl;
        private String remark;
        private String tgGroupId;
        private String tgGroupName;
        private BigDecimal serviceFee;
        private BigDecimal rebateRate;
        private BigDecimal totalConsumption;
        private BigDecimal totalBalance;
        private BigDecimal activationFee;
        private BigDecimal totalByBalance;
        private BigDecimal totalByBalanceU;
        private String usageStatus;
        private Long createdBy;
        private Long updatedBy;
        private LocalDateTime createdAt;
        private LocalDateTime updatedAt;
    }

    /** 渠道费率模型。 */
    @Data
    public static class Rate {
        private Long id;
        private Long channelId;
        private BigDecimal serviceFee;
        private BigDecimal rebateRate;
        private LocalDate effectiveDate;
        private LocalDate expiryDate;
        private Integer status;
        private Long createdBy;
        private Long updatedBy;
        private LocalDateTime createdAt;
        private LocalDateTime updatedAt;
    }

    /** 账户类型模型。 */
    @Data
    public static class AccountType {
        private Long id;
        private String accountType;
        private Long createdBy;
        private LocalDateTime createdAt;
    }

    /** 渠道账户模型。 */
    @Data
    public static class Account {
        private Long id;
        private Long channelId;
        private String accountId;
        private String accountName;
        private String accountType;
        private String fbAccountId;
        private LocalDateTime takeTime;
        private Integer timezone;
        private String bmId;
        private String bmFromFeishu;
        private BigDecimal openingBalance;
        private BigDecimal byBalance;
        private BigDecimal byBalanceU;
        private BigDecimal consumption;
        private BigDecimal balance;
        private BigDecimal actualDeduction;
        private BigDecimal amountSpent;
        private BigDecimal remainingSpendCap;
        private Integer status;
        private boolean synced;
        private Integer usageStatus;
        private String subjectName;
        private Long operatorId;
        private String operatorName;
        private String belongTeam;
        private Long belongTeamId;
        private LocalDate openDate;
        private LocalDateTime assignTime;
        private String remark;
        private Long createdBy;
        private Long updatedBy;
        private LocalDateTime createdAt;
        private LocalDateTime updatedAt;
    }

    /** 广告账户当前所属渠道，用于向账户资产台账补充展示信息。 */
    @Data
    public static class AccountChannel {
        private String accountId;
        private Long channelId;
        private String channelName;
    }

    /** 渠道商品模型。 */
    @Data
    public static class Goods {
        private Long id;
        private Long channelId;
        private String goodsName;
        private String launchRegion;
        private Integer minBuyLimit;
        private BigDecimal rebateRate;
        private String remark;
        private BigDecimal serviceFeeRatio;
        private Integer stockNum;
        private String timezone;
        private Integer putawayStatus;
        private Long createdBy;
        private Long updatedBy;
    }

    /** 广告系列花费模型。 */
    @Data
    public static class Campaign {
        private String campaignId;
        private String campaignName;
        private BigDecimal spendAmount;
        private BigDecimal returnAmount;
    }

    /** 投手选项模型。 */
    @Data
    public static class Pitcher {
        private Long userId;
        private String userName;
        private String nickName;
    }

    /** 部门选项模型。 */
    @Data
    public static class Department {
        private Long id;
        private Long parentId;
        private String label;
        private Integer status;
        private Integer sortOrder;
    }

    /** 渠道及账户统计聚合模型。 */
    @Data
    public static class Aggregate {
        private Long channelCount;
        private Long accountCount;
        private BigDecimal totalConsumption;
        private BigDecimal rechargeAmount;
        private BigDecimal totalBalance;
        private BigDecimal openingBalance;
        private BigDecimal byBalance;
        private BigDecimal byBalanceU;
        private BigDecimal consumption;
        private BigDecimal balance;
        private BigDecimal actualDeduction;
        private BigDecimal amountSpent;
        private BigDecimal remainingSpendCap;
        private Long allCount;
        private Long activeCount;
        private Long closedCount;
        private Long unusedCount;
        private Long usingCount;
        private Long stopCount;
        private Long recycledCount;
        private Long idleCount;
    }

    /** 账户类型维度汇总模型。 */
    @Data
    public static class TypeSummary {
        private Long id;
        private String accountType;
        private String subjectName;
        private String channelName;
        private Integer channelType;
        private BigDecimal totalConsumption;
        private String usageStatus;
    }
}
