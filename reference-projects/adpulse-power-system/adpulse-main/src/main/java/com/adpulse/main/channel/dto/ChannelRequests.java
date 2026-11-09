package com.adpulse.main.channel.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;

/** 渠道管理写入与查询请求。 */
public final class ChannelRequests {
    private ChannelRequests() {}

    /** 渠道列表查询。 */
    public record ChannelQuery(
            String channelName,
            String status,
            String belongTeam,
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate startDate,
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate endDate,
            Integer page,
            Integer pageSize) {}

    /** 渠道周期花费查询；日期按广告面板账户业务日闭区间统计。 */
    public record ChannelPeriodSpendQuery(
            String channelName,
            String status,
            String belongTeam,
            @NotNull LocalDate startDate,
            @NotNull LocalDate endDate,
            Integer page,
            Integer pageSize) {}

    /** 渠道保存请求；修改时未传字段保持原值。 */
    public record ChannelSave(
            @Size(max = 50) String channelName,
            @Size(max = 15) String channelShortName,
            @Size(max = 10) String channelCode,
            Integer channelType,
            @Size(max = 50) String belongTeam,
            Integer status,
            @Size(max = 50) String settlementMethod,
            @Size(max = 10) String settlementCurrency,
            @DecimalMin("0") BigDecimal buyoutAmount,
            @DecimalMin("0") BigDecimal rechargeAmount,
            @Size(max = 1000) String paymentAddress,
            @Size(max = 1000) String loginUrl,
            @Size(max = 500) String remark,
            String tgGroupId,
            @Size(max = 100) String tgGroupName) {}

    /** 费率保存请求。 */
    public record RateSave(
            @NotNull @DecimalMin("0") BigDecimal serviceFee,
            @NotNull @DecimalMin("0") BigDecimal rebateRate,
            @NotNull LocalDate effectiveDate,
            LocalDate expiryDate) {}

    /** 账户类型保存请求。 */
    public record AccountTypeSave(@NotBlank @Size(max = 15) String accountType) {}

    /** 渠道账户分页查询。 */
    public record AccountQuery(
            Long channelId,
            String accountType,
            List<String> accountIds,
            String bmId,
            String subjectName,
            String operatorName,
            Long belongTeamId,
            Integer timezone,
            Integer status,
            Integer usageStatus,
            BigDecimal consumptionMin,
            BigDecimal consumptionMax,
            BigDecimal balanceMin,
            BigDecimal balanceMax,
            LocalDate startDate,
            LocalDate endDate,
            Integer page,
            Integer pageSize,
            List<String> includeFields,
            String keyword) {

        /** 兼容既有渠道账户查询调用，不传台账关键字。 */
        public AccountQuery(
                Long channelId,
                String accountType,
                List<String> accountIds,
                String bmId,
                String subjectName,
                String operatorName,
                Long belongTeamId,
                Integer timezone,
                Integer status,
                Integer usageStatus,
                BigDecimal consumptionMin,
                BigDecimal consumptionMax,
                BigDecimal balanceMin,
                BigDecimal balanceMax,
                LocalDate startDate,
                LocalDate endDate,
                Integer page,
                Integer pageSize,
                List<String> includeFields) {
            this(
                    channelId,
                    accountType,
                    accountIds,
                    bmId,
                    subjectName,
                    operatorName,
                    belongTeamId,
                    timezone,
                    status,
                    usageStatus,
                    consumptionMin,
                    consumptionMax,
                    balanceMin,
                    balanceMax,
                    startDate,
                    endDate,
                    page,
                    pageSize,
                    includeFields,
                    null);
        }
    }

    /** 广告户申请办理时的渠道账户分页查询，不依赖 Doris 花费区间数据。 */
    public record AvailableAccountQuery(
            @NotNull Long channelId,
            String accountType,
            @Size(max = 100) List<@NotBlank @Size(max = 100) String> accountIds,
            Integer timezone,
            Integer status,
            Integer usageStatus,
            @Size(max = 100) List<@NotBlank @Size(max = 100) String> searchKeys,
            Integer page,
            Integer pageSize) {}

    /** 批量分配投手。 */
    public record AccountAssign(
            @NotEmpty List<@NotBlank String> accountIds, @NotNull Long operatorId) {}

    /** 批量修改广告账户名称。 */
    public record AccountNameUpdate(
            @NotBlank @Size(max = 64) String accountId,
            @NotBlank @Size(max = 255) String accountName) {}

    /** 批量更新广告账户归属渠道与账户类型。 */
    public record AccountClassification(
            @NotBlank @Size(max = 64) String accountId,
            @NotNull Long channelId,
            @NotBlank @Size(max = 15) String accountType) {}

    /** 手动建立广告账户、渠道和投手关系。 */
    public record AccountManualAssignment(
            @NotNull Long channelId,
            @NotNull Long operatorId,
            @NotEmpty List<@Valid AccountClassification> accounts) {}

    /** 单个账户批量导入项。 */
    public record AccountImportItem(
            @NotBlank @Size(max = 64) String accountId,
            @NotBlank @Size(max = 15) String accountType) {}

    /** 批量新增渠道账户。 */
    public record AccountBatch(
            @NotNull Long channelId, @NotEmpty List<@Valid AccountImportItem> accounts) {}

    /** 渠道商品保存请求。 */
    public record GoodsSave(
            @NotBlank @Size(max = 100) String goodsName,
            @Size(max = 500) String launchRegion,
            @NotNull @DecimalMin("1") Integer minBuyLimit,
            @NotNull @DecimalMin("0") BigDecimal rebateRate,
            @Size(max = 500) String remark,
            @NotNull @DecimalMin("0") BigDecimal serviceFeeRatio,
            @NotNull @DecimalMin("1") Integer stockNum,
            @Size(max = 500) String timezone) {}

    /** 商品上下架请求。 */
    public record PutawaySave(@NotNull Integer putawayStatus) {}
}
