package com.adpulse.main.cardstation.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

/** 卡台管理接口请求。 */
public final class CardStationRequests {
    private CardStationRequests() {}

    /** 卡片分页筛选条件。 */
    public record CardQuery(
            String platform,
            String cardId,
            String cardName,
            String cardNo,
            String status,
            BigDecimal periodMaxConsumeAmount,
            LocalDate startDate,
            LocalDate endDate,
            Integer page,
            Integer pageSize) {}

    /** 批量限额调整请求。 */
    public record LimitSave(
            @NotEmpty List<String> cardIds,
            @NotNull @DecimalMin("0") BigDecimal limitAmount,
            String preset) {}

    /** 批量冻结或解冻请求。 */
    public record StatusSave(@NotEmpty List<String> ids, @NotNull String status) {}

    /** 卡台限额规则保存请求。 */
    public record LimitRuleSave(
            @NotNull @Min(1) @Max(365) Integer dailyPeriod,
            @NotNull @DecimalMin("0") BigDecimal adjustAmount,
            @NotNull @DecimalMin("0") BigDecimal minAmount,
            @NotNull Boolean autoAdjustEnabled) {}

    /** 卡台自动调额开关请求。 */
    public record AutoAdjustSave(@NotNull Boolean enabled) {}
}
