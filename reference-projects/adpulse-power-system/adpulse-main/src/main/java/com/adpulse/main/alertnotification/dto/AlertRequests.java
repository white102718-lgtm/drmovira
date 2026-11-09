package com.adpulse.main.alertnotification.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;
import java.util.List;

/** 预警通知接口请求。 */
public final class AlertRequests {
    private AlertRequests() {}

    public record RecipientSave(
            @NotBlank String recipientType,
            @NotBlank String recipientKey,
            @NotBlank String recipientName) {}

    public record TestDelivery(@NotEmpty List<@Valid RecipientSave> recipients) {}

    public record ConfigSave(
            @NotNull Boolean enabled,
            @NotNull Boolean banEnabled,
            @NotNull @Min(1) Integer banThreshold,
            @NotNull @Min(1) @Max(720) Integer banWindowValue,
            @NotBlank String banWindowUnit,
            @NotNull Boolean limitChangeEnabled,
            Integer limitPollIntervalMinutes,
            @NotNull List<@Valid RecipientSave> recipients) {}

    /** 封户事件分页查询条件，日期按北京时间自然日解释。 */
    public record EventRecordQuery(
            String keyword,
            LocalDate startDate,
            LocalDate endDate,
            Integer page,
            Integer pageSize) {}

    /** 限额变化事件分页查询条件，日期按北京时间自然日解释。 */
    public record LimitChangeRecordQuery(
            String keyword,
            LocalDate startDate,
            LocalDate endDate,
            String changeType,
            Integer page,
            Integer pageSize) {}
}
