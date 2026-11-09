package com.adpulse.main.channel.doris;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

/** 验证系列层级统计口径、项目名称参数绑定、金额精度及数据源异常边界。 */
class DorisProjectSpendQueryProviderTest {
    private final NamedParameterJdbcTemplate jdbc = mock(NamedParameterJdbcTemplate.class);

    private DorisProjectSpendQueryProvider provider(String catalog) {
        DorisJdbcClient client = mock(DorisJdbcClient.class);
        when(client.jdbc()).thenReturn(jdbc);
        return new DorisProjectSpendQueryProvider(
                client, new DorisProperties(true, null, null, null, null, null, catalog, "ad"));
    }

    @Test
    void sumsOnlyCampaignLevelWithExactProjectNameAndPreservesPrecision() {
        var provider = provider("internal");
        String name = "项目'_%";
        when(jdbc.queryForObject(
                        anyString(), eq(Map.of("projectName", name)), eq(BigDecimal.class)))
                .thenReturn(new BigDecimal("123.456789"));
        assertThat(provider.totalSpend(name)).isEqualByComparingTo("123.456789");
        verify(jdbc)
                .queryForObject(
                        "SELECT COALESCE(SUM(amount_spent), 0) FROM `internal`.`ad`.`ad_daily_detail`"
                                + " WHERE game_platform = :projectName AND level = 'campaign'",
                        Map.of("projectName", name),
                        BigDecimal.class);
    }

    @Test
    void returnsZeroForEmptyAggregate() {
        assertThat(provider("internal").totalSpend("无消耗项目")).isEqualByComparingTo(BigDecimal.ZERO);
    }

    @Test
    void rejectsMissingNamesWithoutQueryingAllProjects() {
        var provider = provider("internal");
        assertThatThrownBy(() -> provider.totalSpend(null)).hasMessageContaining("项目名称不能为空");
        assertThatThrownBy(() -> provider.totalSpend(" ")).hasMessageContaining("项目名称不能为空");
        verifyNoInteractions(jdbc);
    }

    @Test
    void rejectsInvalidCatalog() {
        assertThatThrownBy(() -> provider("internal;drop")).hasMessageContaining("名称不合法");
    }

    @Test
    void doesNotTurnDatabaseFailureIntoZeroSpend() {
        var provider = provider("internal");
        when(jdbc.queryForObject(anyString(), anyMap(), eq(BigDecimal.class)))
                .thenThrow(new DataAccessResourceFailureException("unavailable"));
        assertThatThrownBy(() -> provider.totalSpend("项目"))
                .isInstanceOf(DataAccessResourceFailureException.class);
        assertThatThrownBy(() -> new UnavailableProjectSpendQueryProvider().totalSpend("项目"))
                .hasMessageContaining("未启用");
    }
}
