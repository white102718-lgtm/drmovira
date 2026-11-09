package com.adpulse.main.channel.doris;

import com.adpulse.main.task.service.TaskDeliverySourceProvider;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

/** campaign 层汇总花费与账户/Campaign，ad 层仅收集 Ad Set/Ad。 */
@Component
@ConditionalOnProperty(prefix = "adpulse.doris", name = "enabled", havingValue = "true")
public class DorisTaskDeliverySourceProvider implements TaskDeliverySourceProvider {
    private static final Pattern IDENTIFIER = Pattern.compile("[A-Za-z0-9_]+");
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper json;
    private final String campaignSql;
    private final String adSql;

    public DorisTaskDeliverySourceProvider(
            DorisJdbcClient client, DorisProperties properties, ObjectMapper json) {
        this.jdbc = client.jdbc();
        this.json = json;
        String table =
                quote(properties.spendCatalog())
                        + "."
                        + quote(properties.spendDatabase())
                        + ".`ad_daily_detail`";
        String filters =
                """
                date BETWEEN :startDate AND :endDate
                  AND placer_id = :placerId
                  AND game_platform = :projectName
                  AND agent_line IN (:agencyLineNames)
                  AND LOWER(TRIM(ad_platform)) IN (:platforms)
                """;
        campaignSql =
                ("""
                SELECT ROUND(COALESCE(SUM(CAST(amount_spent AS DECIMAL(18,4))), 0), 2) AS actual_spend,
                    TO_JSON(COLLECT_SET(account_id)) AS account_ids,
                    TO_JSON(COLLECT_SET(campaign_id)) AS campaign_ids
                FROM %s
                WHERE level = 'campaign' AND %s
                """)
                        .formatted(table, filters);
        adSql =
                ("""
                SELECT TO_JSON(COLLECT_SET(ad_set_id)) AS adset_ids,
                    TO_JSON(COLLECT_SET(ad_id)) AS ad_ids
                FROM %s
                WHERE level = 'ad' AND %s
                """)
                        .formatted(table, filters);
    }

    @Override
    public Facts query(
            LocalDate startDate,
            LocalDate endDate,
            String placerId,
            String projectName,
            List<String> agencyLineNames,
            List<String> platforms) {
        var parameters =
                new MapSqlParameterSource()
                        .addValue("startDate", startDate)
                        .addValue("endDate", endDate)
                        .addValue("placerId", placerId)
                        .addValue("projectName", projectName)
                        .addValue("agencyLineNames", agencyLineNames)
                        .addValue("platforms", platforms);
        try {
            CampaignFacts campaign =
                    jdbc.queryForObject(
                            campaignSql,
                            parameters,
                            (rs, index) ->
                                    new CampaignFacts(
                                            ids(rs.getString("account_ids")),
                                            ids(rs.getString("campaign_ids")),
                                            rs.getBigDecimal("actual_spend")));
            AdFacts ad =
                    jdbc.queryForObject(
                            adSql,
                            parameters,
                            (rs, index) ->
                                    new AdFacts(
                                            ids(rs.getString("adset_ids")),
                                            ids(rs.getString("ad_ids"))));
            return new Facts(
                    campaign.accountIds(),
                    campaign.campaignIds(),
                    ad.adsetIds(),
                    ad.adIds(),
                    campaign.actualSpend());
        } catch (DataAccessException exception) {
            throw new IllegalStateException("投放中心数据暂不可用，请稍后重试", exception);
        }
    }

    private List<String> ids(String value) {
        if (value == null || value.isBlank()) return List.of();
        try {
            return json.readValue(value, new TypeReference<List<String>>() {}).stream()
                    .filter(id -> id != null && !id.isBlank())
                    .distinct()
                    .sorted()
                    .toList();
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Doris交付对象ID格式错误", exception);
        }
    }

    private static String quote(String value) {
        if (value == null || !IDENTIFIER.matcher(value).matches()) {
            throw new IllegalArgumentException("Doris Catalog或数据库名称不合法");
        }
        return "`" + value + "`";
    }

    private record CampaignFacts(
            List<String> accountIds, List<String> campaignIds, BigDecimal actualSpend) {}

    private record AdFacts(List<String> adsetIds, List<String> adIds) {}
}
