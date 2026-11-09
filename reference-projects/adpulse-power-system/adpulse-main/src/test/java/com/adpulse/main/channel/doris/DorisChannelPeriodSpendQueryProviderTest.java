package com.adpulse.main.channel.doris;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.channel.dto.ChannelRequests.ChannelPeriodSpendQuery;
import com.adpulse.main.channel.service.ChannelPeriodSpendQueryProvider.Item;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

/** 验证渠道周期花费的层级、日期、稳定渠道归属、筛选和分页查询契约。 */
class DorisChannelPeriodSpendQueryProviderTest {
    @Test
    void queriesCampaignSpendByLatestStableChannelAssignment() {
        NamedParameterJdbcTemplate jdbc = mock(NamedParameterJdbcTemplate.class);
        DorisJdbcClient client = mock(DorisJdbcClient.class);
        when(client.jdbc()).thenReturn(jdbc);
        var provider =
                new DorisChannelPeriodSpendQueryProvider(
                        client,
                        new DorisProperties(
                                true,
                                null,
                                null,
                                null,
                                "mysql_adpulse_system",
                                "adpulse_system",
                                "internal",
                                "ad"));
        when(jdbc.query(anyString(), any(MapSqlParameterSource.class), any(RowMapper.class)))
                .thenReturn(List.of(new Item(7L, new BigDecimal("128.50"))));
        when(jdbc.queryForObject(
                        anyString(), any(MapSqlParameterSource.class), eq(BigDecimal.class)))
                .thenReturn(new BigDecimal("256.75"));

        var result =
                provider.query(
                        new ChannelPeriodSpendQuery(
                                "Meta",
                                "1",
                                "Mpower",
                                LocalDate.of(2026, 9, 1),
                                LocalDate.of(2026, 9, 23),
                                2,
                                10),
                        10,
                        10);

        assertThat(result.items()).containsExactly(new Item(7L, new BigDecimal("128.50")));
        assertThat(result.totalConsumption()).isEqualByComparingTo("256.75");

        ArgumentCaptor<String> sql = ArgumentCaptor.forClass(String.class);
        ArgumentCaptor<MapSqlParameterSource> parameters =
                ArgumentCaptor.forClass(MapSqlParameterSource.class);
        verify(jdbc).query(sql.capture(), parameters.capture(), any(RowMapper.class));
        assertThat(sql.getValue())
                .contains(
                        "spend.`level` = 'campaign'",
                        "spend.`date` >= :startDate",
                        "spend.`date` <= :endDate",
                        "newer.id > asset.id",
                        "s.channel_id = c.id",
                        "c.channel_name LIKE :channelName",
                        "c.status = :status",
                        "c.belong_team = :belongTeam",
                        "LIMIT :offset, :pageSize");
        assertThat(parameters.getValue().getValue("startDate")).isEqualTo(LocalDate.of(2026, 9, 1));
        assertThat(parameters.getValue().getValue("endDate")).isEqualTo(LocalDate.of(2026, 9, 23));
        assertThat(parameters.getValue().getValue("offset")).isEqualTo(10);
        assertThat(parameters.getValue().getValue("pageSize")).isEqualTo(10);
    }
}
