package com.adpulse.main.channel.doris;

import com.adpulse.main.project.service.ProjectSpendQueryProvider;
import java.math.BigDecimal;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

/** 使用独立 Doris 客户端按项目名称汇总广告消耗。 */
@Component
@ConditionalOnProperty(prefix = "adpulse.doris", name = "enabled", havingValue = "true")
public class DorisProjectSpendQueryProvider implements ProjectSpendQueryProvider {
    private final NamedParameterJdbcTemplate jdbc;
    private final String spendTable;

    public DorisProjectSpendQueryProvider(DorisJdbcClient client, DorisProperties properties) {
        jdbc = client.jdbc();
        spendTable =
                quote(properties.spendCatalog())
                        + "."
                        + quote(properties.spendDatabase())
                        + ".`ad_daily_detail`";
    }

    /** 账户可跨项目投放，按系列所属项目汇总消耗；仅取系列层级，避免跨层级重复计算。 */
    @Override
    public BigDecimal totalSpend(String projectName) {
        if (projectName == null || projectName.isBlank()) {
            throw new IllegalArgumentException("项目名称不能为空");
        }
        BigDecimal amount =
                jdbc.queryForObject(
                        "SELECT COALESCE(SUM(amount_spent), 0) FROM "
                                + spendTable
                                + " WHERE game_platform = :projectName AND level = 'campaign'",
                        Map.of("projectName", projectName),
                        BigDecimal.class);
        return amount == null ? BigDecimal.ZERO : amount;
    }

    private static String quote(String value) {
        if (value == null || !value.matches("[A-Za-z0-9_]+")) {
            throw new IllegalArgumentException("Doris Catalog或数据库名称不合法");
        }
        return "`" + value + "`";
    }
}
