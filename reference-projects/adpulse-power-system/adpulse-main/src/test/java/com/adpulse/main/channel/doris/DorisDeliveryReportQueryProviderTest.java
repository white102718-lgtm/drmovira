package com.adpulse.main.channel.doris;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.adpulse.main.deliveryreport.DeliveryReportTypes.PlatformRow;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.ArgumentMatchers;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

/** 验证campaign单层、本人过滤、项目代理线分组和首购字段约定。 */
class DorisDeliveryReportQueryProviderTest {
    @Test
    void batchSpendUsesBoundRangeAndUsersWithoutCollectingSourceIds() {
        var jdbc = mock(NamedParameterJdbcTemplate.class);
        var client = mock(DorisJdbcClient.class);
        when(client.jdbc()).thenReturn(jdbc);
        var provider =
                new DorisDeliveryReportQueryProvider(
                        client,
                        new DorisProperties(true, null, null, null, null, null, "internal", "ad"),
                        new ObjectMapper());
        var start = LocalDate.of(2026, 9, 1);
        var end = start.plusDays(10);
        provider.querySpend(start, end, List.of("Alice", "Bob'"));
        var sql = ArgumentCaptor.forClass(String.class);
        var params = ArgumentCaptor.forClass(MapSqlParameterSource.class);
        verify(jdbc)
                .query(
                        sql.capture(),
                        params.capture(),
                        ArgumentMatchers
                                .<RowMapper<
                                                com.adpulse.main.deliveryreport.DeliveryReportTypes
                                                        .SpendRow>>
                                        any());
        assertThat(sql.getValue())
                .contains(
                        "BETWEEN :startDate AND :endDate", "IN (:placerIds)", "level = 'campaign'")
                .doesNotContain("COLLECT_SET", "Bob", "Alice");
        assertThat(params.getValue().getValue("placerIds")).isEqualTo(List.of("Alice", "Bob'"));
        clearInvocations(jdbc);
        assertThat(provider.querySpend(start, end, List.of())).isEmpty();
        verifyNoInteractions(jdbc);
    }

    @Test
    void bindsUserAndDateAndAggregatesCampaignOnly() {
        var jdbc = mock(NamedParameterJdbcTemplate.class);
        var client = mock(DorisJdbcClient.class);
        when(client.jdbc()).thenReturn(jdbc);
        when(jdbc.query(
                        anyString(),
                        any(MapSqlParameterSource.class),
                        ArgumentMatchers.<RowMapper<PlatformRow>>any()))
                .thenReturn(List.of());
        var provider =
                new DorisDeliveryReportQueryProvider(
                        client,
                        new DorisProperties(true, null, null, null, null, null, "internal", "ad"),
                        new ObjectMapper());
        LocalDate date = LocalDate.of(2026, 9, 9);
        provider.query(date, "Alice' OR 1=1");
        var sql = ArgumentCaptor.forClass(String.class);
        var params = ArgumentCaptor.forClass(MapSqlParameterSource.class);
        verify(jdbc)
                .query(
                        sql.capture(),
                        params.capture(),
                        ArgumentMatchers.<RowMapper<PlatformRow>>any());
        assertThat(sql.getValue())
                .contains(
                        "level = 'campaign'",
                        "placer_id = :placerId",
                        "date = :date",
                        "GROUP BY date, game_platform, agent_line, placer_id",
                        "SUM(purchases)",
                        "COLLECT_SET(campaign_id)");
        assertThat(sql.getValue()).doesNotContain("Alice");
        assertThat(params.getValue().getValue("placerId")).isEqualTo("Alice' OR 1=1");
        assertThat(params.getValue().getValue("date")).isEqualTo(date);
    }
}
