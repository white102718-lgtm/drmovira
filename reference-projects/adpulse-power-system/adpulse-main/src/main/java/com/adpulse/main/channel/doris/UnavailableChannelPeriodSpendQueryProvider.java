package com.adpulse.main.channel.doris;

import com.adpulse.main.channel.dto.ChannelRequests.ChannelPeriodSpendQuery;
import com.adpulse.main.channel.service.ChannelPeriodSpendQueryProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Doris 未启用时明确拒绝周期花费查询，禁止以零值伪装为真实消耗。 */
@Component
@ConditionalOnProperty(
        prefix = "adpulse.doris",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true)
public class UnavailableChannelPeriodSpendQueryProvider implements ChannelPeriodSpendQueryProvider {
    @Override
    public Result query(ChannelPeriodSpendQuery query, int offset, int pageSize) {
        throw new IllegalStateException("Doris 渠道花费查询数据源未启用");
    }
}
