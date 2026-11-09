package com.adpulse.main.alertnotification.dto;

import com.adpulse.main.alertnotification.model.AlertModels.Config;
import com.adpulse.main.alertnotification.model.AlertModels.Recipient;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/** 预警通知接口视图。 */
public final class AlertViews {
    private AlertViews() {}

    public record Settings(Config config, List<Recipient> recipients) {}

    public record TestDeliveryResult(int successCount, int failedCount) {}

    public record Page<T>(List<T> items, long total, int page, int pageSize) {}

    /** Facebook 平台同步产生的一条封户事件。 */
    public record BanRecord(
            String id,
            String accountId,
            String accountName,
            Integer previousStatus,
            Integer currentStatus,
            String disableReason,
            String currency,
            LocalDateTime occurredAt,
            String source) {}

    /** Facebook 平台同步产生的一条账户日限额变化事件。 */
    public record LimitChangeRecord(
            String id,
            String accountId,
            String accountName,
            BigDecimal previousLimit,
            BigDecimal currentLimit,
            String currency,
            String changeType,
            LocalDateTime occurredAt,
            String source) {}
}
