package com.adpulse.main.channel.doris;

import com.adpulse.main.deliveryreport.DeliveryReportException;
import com.adpulse.main.deliveryreport.DeliveryReportQueryProvider;
import com.adpulse.main.deliveryreport.DeliveryReportTypes.PlatformRow;
import java.time.LocalDate;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Doris未配置时明确失败，避免生成错误的零消耗日报。 */
@Component
@ConditionalOnProperty(
        prefix = "adpulse.doris",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true)
public class UnavailableDeliveryReportQueryProvider implements DeliveryReportQueryProvider {
    @Override
    public List<com.adpulse.main.deliveryreport.DeliveryReportTypes.SpendRow> querySpend(
            LocalDate startDate, LocalDate endDate, List<String> placerIds) {
        if (placerIds.isEmpty()) return List.of();
        throw new DeliveryReportException("平台数据源尚未启用，请联系管理员");
    }

    @Override
    public List<PlatformRow> query(LocalDate date, String placerId) {
        throw new DeliveryReportException("平台数据源尚未启用，请联系管理员");
    }
}
