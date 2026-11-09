package com.adpulse.main.channel.doris;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendRequests.TaskLine;
import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendViews.TaskLineSpend;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Collection;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.ArgumentMatchers;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

/** 验证素材师月报花费的项目和代理线精确筛选条件。 */
class DorisMaterialSettlementSpendQueryProviderTest {
    private final NamedParameterJdbcTemplate jdbc = mock(NamedParameterJdbcTemplate.class);

    private DorisMaterialSettlementSpendQueryProvider provider(String catalog) {
        DorisJdbcClient client = mock(DorisJdbcClient.class);
        when(client.jdbc()).thenReturn(jdbc);
        return new DorisMaterialSettlementSpendQueryProvider(
                client, new DorisProperties(true, null, null, null, null, null, catalog, "ad"));
    }

    @Test
    void queriesOnlySelectedTaskLinesInEachProject() {
        when(jdbc.query(
                        anyString(),
                        any(MapSqlParameterSource.class),
                        ArgumentMatchers.<RowMapper<TaskLineSpend>>any()))
                .thenReturn(
                        List.of(
                                new TaskLineSpend(
                                        "EE666",
                                        "1002-FB-PWA-164",
                                        new BigDecimal("139.81"),
                                        "USD")));

        List<TaskLineSpend> result =
                provider("internal")
                        .query(
                                LocalDate.of(2026, 9, 1),
                                LocalDate.of(2026, 9, 30),
                                List.of(
                                        new TaskLine("EE666", "1002-FB-PWA-164"),
                                        new TaskLine("EE666", "EE666-1002-FB-PWA-104")));

        ArgumentCaptor<String> sql = ArgumentCaptor.forClass(String.class);
        @SuppressWarnings("unchecked")
        ArgumentCaptor<MapSqlParameterSource> parameters =
                ArgumentCaptor.forClass(MapSqlParameterSource.class);
        verify(jdbc)
                .query(
                        sql.capture(),
                        parameters.capture(),
                        ArgumentMatchers.<RowMapper<TaskLineSpend>>any());

        assertThat(sql.getValue())
                .contains("agent_line IN (:taskLineNames)")
                .contains("level = 'ad'")
                .contains("date >= :startDate")
                .contains("date <= :endDate");
        assertThat(parameters.getValue().getValue("projectName")).isEqualTo("EE666");
        @SuppressWarnings("unchecked")
        Collection<String> taskLineNames =
                (Collection<String>) parameters.getValue().getValue("taskLineNames");
        assertThat(taskLineNames)
                .containsExactlyInAnyOrder("1002-FB-PWA-164", "EE666-1002-FB-PWA-104");
        assertThat(parameters.getValue().getValue("startDate")).isEqualTo(LocalDate.of(2026, 9, 1));
        assertThat(parameters.getValue().getValue("endDate")).isEqualTo(LocalDate.of(2026, 9, 30));
        assertThat(result).hasSize(1);
        assertThat(result.getFirst().amount()).isEqualByComparingTo("139.81");
    }

    @Test
    void rejectsInvalidDorisIdentifier() {
        assertThatThrownBy(() -> provider("internal;drop"))
                .hasMessageContaining("Catalog或数据库名称不合法");
    }

    @Test
    void unavailableProviderDoesNotReturnZeroSpend() {
        assertThatThrownBy(
                        () ->
                                new UnavailableMaterialSettlementSpendQueryProvider()
                                        .query(
                                                LocalDate.of(2026, 9, 1),
                                                LocalDate.of(2026, 9, 30),
                                                List.of(new TaskLine("EE666", "1002-FB-PWA-164"))))
                .hasMessageContaining("数据源未启用");
    }
}
