package com.adpulse.main.channel.doris;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import com.adpulse.main.channel.dto.ChannelRequests.AccountQuery;
import java.math.BigDecimal;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

/** Doris 跨 Catalog 广告账户资产与日花费联合查询集成测试。 */
class DorisAccountQueryProviderIntegrationTest {

    @Test
    void shouldQueryAssetLedgerAndDorisSpendTableTogether() {
        String url = System.getenv("DORIS_URL");
        assumeTrue(url != null && !url.isBlank(), "未配置Doris连接时跳过集成测试");
        DorisProperties properties =
                new DorisProperties(
                        true,
                        url,
                        System.getenv("DORIS_USERNAME"),
                        System.getenv("DORIS_PASSWORD"),
                        value("DORIS_MYSQL_CATALOG", "mysql_adpulse_system"),
                        value("DORIS_MYSQL_DATABASE", "adpulse_system"),
                        value("DORIS_SPEND_CATALOG", "internal"),
                        value("DORIS_SPEND_DATABASE", "ad"));

        try (DorisJdbcClient client = new DorisJdbcClient(properties)) {
            DorisAccountQueryProvider provider = new DorisAccountQueryProvider(client, properties);
            LocalDate today = LocalDate.now();
            AccountQuery query =
                    new AccountQuery(
                            null,
                            null,
                            null,
                            null,
                            null,
                            null,
                            null,
                            null,
                            null,
                            null,
                            BigDecimal.ZERO,
                            null,
                            null,
                            null,
                            today,
                            today,
                            1,
                            10,
                            null);

            var page = provider.find(query, 0, 10);
            var aggregate = provider.summarize(query);

            assertThat(page.items()).hasSizeLessThanOrEqualTo(10);
            assertThat(page.total()).isGreaterThanOrEqualTo(page.items().size());
            assertThat(aggregate).isNotNull();
            assertThat(aggregate.getConsumption()).isNotNull();
        }
    }

    private String value(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
