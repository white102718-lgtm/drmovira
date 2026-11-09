package com.adpulse.main.channel.service;

import com.adpulse.main.channel.dto.ChannelRequests.ChannelPeriodSpendQuery;
import java.math.BigDecimal;
import java.util.List;

/** 按广告面板口径查询渠道周期花费的数据源边界。 */
public interface ChannelPeriodSpendQueryProvider {
    /** 查询当前页渠道花费，并返回相同筛选范围内不受分页影响的合计。 */
    Result query(ChannelPeriodSpendQuery query, int offset, int pageSize);

    /** 单个稳定渠道 ID 的周期花费。 */
    record Item(Long channelId, BigDecimal totalConsumption) {}

    /** 当前页明细及全部筛选结果合计。 */
    record Result(List<Item> items, BigDecimal totalConsumption) {}
}
