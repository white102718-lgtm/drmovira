package com.adpulse.main.channel.doris;

import com.adpulse.main.task.service.TaskDeliverySourceProvider;
import java.time.LocalDate;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Doris 未启用时显式拒绝同步，不把缺数当作零消耗。 */
@Component
@ConditionalOnProperty(
        prefix = "adpulse.doris",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true)
public class UnavailableTaskDeliverySourceProvider implements TaskDeliverySourceProvider {
    @Override
    public Facts query(
            LocalDate startDate,
            LocalDate endDate,
            String placerId,
            String projectName,
            List<String> agencyLineNames,
            List<String> platforms) {
        throw new IllegalStateException("投放中心数据源未启用");
    }
}
