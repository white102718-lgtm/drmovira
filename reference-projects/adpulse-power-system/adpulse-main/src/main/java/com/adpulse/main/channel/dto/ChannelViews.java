package com.adpulse.main.channel.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

/** 渠道管理响应模型。 */
public final class ChannelViews {
    private ChannelViews() {}

    /** 通用分页响应。 */
    public record Page<T>(List<T> items, long total, int page, int pageSize) {}

    /** 渠道详情及列表聚合字段。 */
    public record ChannelDetail(
            String id,
            String channelName,
            String channelShortName,
            String channelCode,
            Integer channelType,
            String belongTeam,
            Integer status,
            Integer putawayStatus,
            String settlementMethod,
            String settlementCurrency,
            BigDecimal buyoutAmount,
            BigDecimal rechargeAmount,
            String paymentAddress,
            String loginUrl,
            String remark,
            String tgGroupId,
            String tgGroupName,
            BigDecimal serviceFee,
            BigDecimal rebateRate,
            BigDecimal totalConsumption,
            BigDecimal totalBalance,
            BigDecimal activationFee,
            BigDecimal totalByBalance,
            BigDecimal totalByBalanceU,
            String usageStatus,
            // 保留数据库 DATETIME 的时间值，由后端格式化，前端直接展示以避免浏览器时区转换。
            @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd HH:mm:ss")
                    LocalDateTime createTime,
            LocalDateTime updateTime) {}

    /** 渠道汇总。 */
    public record ChannelSummary(
            long channelCount,
            long accountCount,
            BigDecimal totalConsumption,
            BigDecimal rechargeAmount,
            BigDecimal totalBalance) {}

    /** 单个渠道在所选广告业务日期内的花费。 */
    public record ChannelPeriodSpendItem(String channelId, BigDecimal totalConsumption) {}

    /** 渠道周期花费分页结果及全部筛选结果的合计。 */
    public record ChannelPeriodSpend(
            List<ChannelPeriodSpendItem> items,
            BigDecimal totalConsumption,
            int page,
            int pageSize) {}

    /** 打款申请选择渠道后自动回填的只读业务数据。 */
    public record ChannelPaymentContext(
            String channelId,
            String channelName,
            BigDecimal channelYesterdayCost,
            String paymentAddress) {}

    /** 账户类型维度渠道汇总。 */
    public record ChannelTypeSummary(
            String id,
            String accountType,
            String subjectName,
            String channelName,
            Integer channelType,
            BigDecimal totalConsumption,
            String usageStatus) {}

    /** 渠道费率。 */
    public record Rate(
            String id,
            String channelId,
            BigDecimal serviceFee,
            BigDecimal rebateRate,
            LocalDate effectiveDate,
            LocalDate expiryDate,
            Integer status,
            LocalDateTime createTime,
            LocalDateTime updateTime) {}

    /** 渠道账户类型。 */
    public record AccountType(String id, String accountType, LocalDateTime createTime) {}

    /** 渠道关联广告账户。 */
    public record Account(
            String channelId,
            String accountId,
            String accountName,
            String accountType,
            String fbAccountId,
            LocalDateTime takeTime,
            Integer timezone,
            String bmId,
            String bmFromFeishu,
            BigDecimal openingBalance,
            BigDecimal byBalance,
            BigDecimal byBalanceU,
            BigDecimal consumption,
            BigDecimal balance,
            BigDecimal actualDeduction,
            BigDecimal amountSpent,
            BigDecimal remainingSpendCap,
            Integer status,
            boolean synced,
            Integer usageStatus,
            String subjectName,
            String operatorId,
            String operatorName,
            String belongTeam,
            String belongTeamId,
            LocalDate openDate,
            LocalDateTime createTime,
            LocalDateTime assignTime,
            String remark) {}

    /** 账户金额汇总。 */
    public record AccountStatistics(
            BigDecimal openingBalance,
            BigDecimal byBalance,
            BigDecimal byBalanceU,
            BigDecimal consumption,
            BigDecimal balance,
            BigDecimal actualDeduction,
            BigDecimal amountSpent,
            BigDecimal remainingSpendCap) {}

    /** 账户状态数量汇总。 */
    public record AccountCounts(
            long allCount,
            long activeCount,
            long closedCount,
            long unusedCount,
            long usingCount,
            long stopCount,
            long recycledCount,
            long idleCount) {}

    /** 渠道上架商品。 */
    public record Goods(
            String channelId,
            String goodsName,
            String launchRegion,
            Integer minBugLimit,
            BigDecimal rebateRate,
            String remark,
            BigDecimal serviceFeeRatio,
            Integer stockNum,
            String timezone,
            Integer putawayStatus) {}

    /** 广告系列花费。 */
    public record CampaignSpend(
            String campaignId,
            String campaignName,
            BigDecimal spendAmount,
            BigDecimal returnAmount) {}

    /** 可分配投手。 */
    public record Pitcher(String userId, String userName, String nickName) {}

    /** 部门树节点。 */
    public record Department(
            String id, String label, boolean disabled, List<Department> children) {}
}
