package com.adpulse.main.channel.doris;

import com.adpulse.main.project.service.ProjectSpendQueryProvider;
import java.math.BigDecimal;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Doris 未启用时明确拒绝查询，避免将数据不可用误报为零消耗。 */
@Component
@ConditionalOnProperty(
        prefix = "adpulse.doris",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true)
public class UnavailableProjectSpendQueryProvider implements ProjectSpendQueryProvider {
    /** 未配置数据源时报告不可用。 */
    @Override
    public BigDecimal totalSpend(String projectName) {
        throw new IllegalStateException("Doris项目消耗查询数据源未启用");
    }
}
