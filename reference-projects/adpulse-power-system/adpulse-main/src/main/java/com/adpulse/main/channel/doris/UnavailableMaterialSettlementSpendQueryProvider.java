package com.adpulse.main.channel.doris;

import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendRequests.TaskLine;
import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendViews.TaskLineSpend;
import com.adpulse.main.materialsettlement.service.MaterialSettlementSpendQueryProvider;
import java.time.LocalDate;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Doris 未启用时拒绝素材师月报花费查询，避免将数据不可用误报为零花费。 */
@Component
@ConditionalOnProperty(
        prefix = "adpulse.doris",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true)
public class UnavailableMaterialSettlementSpendQueryProvider
        implements MaterialSettlementSpendQueryProvider {
    @Override
    public List<TaskLineSpend> query(
            LocalDate startDate, LocalDate endDate, List<TaskLine> taskLines) {
        throw new IllegalStateException("Doris素材师月报花费查询数据源未启用");
    }
}
