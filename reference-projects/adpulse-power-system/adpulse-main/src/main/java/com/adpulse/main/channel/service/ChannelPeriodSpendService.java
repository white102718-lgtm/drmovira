package com.adpulse.main.channel.service;

import com.adpulse.main.channel.dto.ChannelRequests.ChannelPeriodSpendQuery;
import com.adpulse.main.channel.dto.ChannelViews;
import java.math.BigDecimal;
import org.springframework.stereotype.Service;

/** 校验渠道周期花费查询，并将 Doris 结果适配为渠道管理响应。 */
@Service
public class ChannelPeriodSpendService {
    private final ChannelPeriodSpendQueryProvider provider;

    public ChannelPeriodSpendService(ChannelPeriodSpendQueryProvider provider) {
        this.provider = provider;
    }

    /** 查询与广告面板渠道维度一致的周期花费。 */
    public ChannelViews.ChannelPeriodSpend query(ChannelPeriodSpendQuery query) {
        if (query.startDate() == null || query.endDate() == null) {
            throw new ChannelService.ChannelException("请选择完整的花费周期");
        }
        if (query.startDate().isAfter(query.endDate())) {
            throw new ChannelService.ChannelException("花费周期开始日期不能晚于结束日期");
        }
        int page = query.page() == null || query.page() < 1 ? 1 : query.page();
        int pageSize =
                query.pageSize() == null
                        ? 10
                        : Math.min(Math.max(query.pageSize(), 1), 1_000_000);
        try {
            var result = provider.query(query, (page - 1) * pageSize, pageSize);
            var items =
                    result.items().stream()
                            .map(
                                    item ->
                                            new ChannelViews.ChannelPeriodSpendItem(
                                                    Long.toString(item.channelId()),
                                                    money(item.totalConsumption())))
                            .toList();
            return new ChannelViews.ChannelPeriodSpend(
                    items, money(result.totalConsumption()), page, pageSize);
        } catch (ChannelService.ChannelException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new ChannelService.ChannelException(
                    "广告面板花费数据暂不可用，请稍后重试", exception);
        }
    }

    private BigDecimal money(BigDecimal value) {
        return value == null ? BigDecimal.ZERO : value;
    }
}
