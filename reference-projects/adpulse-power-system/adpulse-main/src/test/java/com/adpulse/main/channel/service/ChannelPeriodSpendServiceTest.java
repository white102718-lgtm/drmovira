package com.adpulse.main.channel.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.channel.dto.ChannelRequests.ChannelPeriodSpendQuery;
import com.adpulse.main.channel.service.ChannelPeriodSpendQueryProvider.Item;
import com.adpulse.main.channel.service.ChannelPeriodSpendQueryProvider.Result;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.Test;

/** 验证渠道周期花费的日期边界、分页和数据源失败语义。 */
class ChannelPeriodSpendServiceTest {
    private final ChannelPeriodSpendQueryProvider provider =
            mock(ChannelPeriodSpendQueryProvider.class);
    private final ChannelPeriodSpendService service = new ChannelPeriodSpendService(provider);

    @Test
    void returnsPageItemsAndUnpagedTotal() {
        var query = query(LocalDate.of(2026, 9, 1), LocalDate.of(2026, 9, 23));
        when(provider.query(query, 10, 10))
                .thenReturn(
                        new Result(
                                List.of(new Item(7L, new BigDecimal("128.50"))),
                                new BigDecimal("256.75")));

        var result = service.query(query);

        assertThat(result.items().getFirst().channelId()).isEqualTo("7");
        assertThat(result.items().getFirst().totalConsumption()).isEqualByComparingTo("128.50");
        assertThat(result.totalConsumption()).isEqualByComparingTo("256.75");
        assertThat(result.page()).isEqualTo(2);
        verify(provider).query(query, 10, 10);
    }

    @Test
    void rejectsReversedDatesBeforeQueryingDoris() {
        assertThatThrownBy(
                        () ->
                                service.query(
                                        query(LocalDate.of(2026, 9, 23), LocalDate.of(2026, 9, 1))))
                .isInstanceOf(ChannelService.ChannelException.class)
                .hasMessageContaining("开始日期");
    }

    @Test
    void reportsDorisFailureWithoutReturningZero() {
        var query = query(LocalDate.of(2026, 9, 1), LocalDate.of(2026, 9, 23));
        when(provider.query(any(), eq(10), eq(10)))
                .thenThrow(new IllegalStateException("unavailable"));

        assertThatThrownBy(() -> service.query(query))
                .isInstanceOf(ChannelService.ChannelException.class)
                .hasMessageContaining("暂不可用");
    }

    private ChannelPeriodSpendQuery query(LocalDate startDate, LocalDate endDate) {
        return new ChannelPeriodSpendQuery("Meta", "1", "Mpower", startDate, endDate, 2, 10);
    }
}
