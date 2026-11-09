package com.adpulse.main.cardstation.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/** 卡台管理接口响应。 */
public final class CardStationViews {
    private CardStationViews() {}

    /** 通用分页响应。 */
    public record Page<T>(List<T> items, long total, int page, int pageSize) {}

    /** 兼容两个卡台原型字段的卡片响应。 */
    public record Card(
            String id,
            String cardId,
            String cardName,
            String nickname,
            String maskedPan,
            String cardNumber,
            String status,
            String cardStatus,
            BigDecimal balance,
            BigDecimal cardBalance,
            String currency,
            String cardCurrency,
            String advertisementAccountId,
            String companyEntity,
            BigDecimal dailyLimit,
            BigDecimal monthlyLimit,
            BigDecimal transactionMinAmount,
            BigDecimal transactionMaxAmount,
            BigDecimal utilizationLimitAmount,
            String utilizationLimitPreset,
            BigDecimal periodMaxConsumeAmount,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {}

    /** 卡台账户余额。 */
    public record Balance(
            String productCode, String currency, BigDecimal balance, BigDecimal frozenBalance) {}

    /** 卡片统计。 */
    public record Statistics(long total, long active, long frozen, BigDecimal balance) {}

    /** 限额调整记录。 */
    public record LimitRecord(
            String id,
            String cardId,
            BigDecimal oldAmount,
            BigDecimal newAmount,
            String preset,
            Integer status,
            String errorMessage,
            LocalDateTime createdAt) {}

    /** 已进入新服务队列的同步任务。 */
    public record SyncJob(String id, String provider, Integer status) {}

    /** PhotonPay与ArrivalX共用的卡日授权额度规则。 */
    public record LimitRule(
            boolean configured,
            Integer dailyPeriod,
            BigDecimal adjustAmount,
            BigDecimal minAmount,
            boolean autoAdjustEnabled,
            LocalDateTime updatedAt) {}
}
