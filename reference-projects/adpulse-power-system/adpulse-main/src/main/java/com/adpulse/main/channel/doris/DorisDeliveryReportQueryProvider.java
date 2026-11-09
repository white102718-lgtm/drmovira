package com.adpulse.main.channel.doris;

import com.adpulse.main.deliveryreport.DeliveryReportException;
import com.adpulse.main.deliveryreport.DeliveryReportQueryProvider;
import com.adpulse.main.deliveryreport.DeliveryReportTypes.PlatformRow;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDate;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

/** campaign层本人日报取数，禁止同时累加account、adset和ad层。 */
@Component
@ConditionalOnProperty(prefix = "adpulse.doris", name = "enabled", havingValue = "true")
public class DorisDeliveryReportQueryProvider implements DeliveryReportQueryProvider {
    private static final Pattern IDENTIFIER = Pattern.compile("[A-Za-z0-9_]+");
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper json;
    private final String sql;
    private final String spendSql;

    public DorisDeliveryReportQueryProvider(
            DorisJdbcClient client, DorisProperties properties, ObjectMapper json) {
        this.jdbc = client.jdbc();
        this.json = json;
        String table =
                quote(properties.spendCatalog())
                        + "."
                        + quote(properties.spendDatabase())
                        + ".`ad_daily_detail`";
        spendSql =
                """
                SELECT date, placer_id, game_platform AS project_name,
                    agent_line AS agency_line_name, LOWER(TRIM(ad_platform)) AS platform,
                    ROUND(COALESCE(SUM(CAST(amount_spent AS DECIMAL(18,4))), 0), 2) AS actual_spend
                FROM %s
                WHERE date BETWEEN :startDate AND :endDate
                  AND placer_id IN (:placerIds) AND level = 'campaign'
                GROUP BY date, placer_id, game_platform, agent_line, LOWER(TRIM(ad_platform))
                """
                        .formatted(table);
        sql =
                """
                SELECT game_platform AS project_name,
                    agent_line AS agency_line_name,
                    LOWER(TRIM(ad_platform)) AS platform,
                    ROUND(COALESCE(SUM(CAST(amount_spent AS DECIMAL(18,4))), 0), 2) AS actual_spend,
                    COALESCE(SUM(impressions), 0) AS impressions,
                    COALESCE(SUM(clicks_all), 0) AS clicks,
                    COALESCE(SUM(app_installs), 0) AS installs,
                    COALESCE(SUM(complete_registration), 0) AS registrations,
                    COALESCE(SUM(purchases), 0) AS first_purchases,
                    TO_JSON(COLLECT_SET(account_id)) AS account_ids,
                    TO_JSON(COLLECT_SET(campaign_id)) AS campaign_ids
                FROM %s
                WHERE date = :date
                  AND placer_id = :placerId
                  AND level = 'campaign'
                GROUP BY date, game_platform, agent_line, placer_id, LOWER(TRIM(ad_platform))
                ORDER BY game_platform, agent_line, platform
                """
                        .formatted(table);
    }

    /** 日期直接使用Doris业务日期；业务已确认 purchases 为账户内首购口径。 */
    @Override
    public List<PlatformRow> query(LocalDate date, String placerId) {
        try {
            return jdbc.query(
                    sql,
                    new MapSqlParameterSource()
                            .addValue("date", date)
                            .addValue("placerId", placerId),
                    (rs, index) ->
                            new PlatformRow(
                                    rs.getString("project_name"),
                                    rs.getString("agency_line_name"),
                                    rs.getString("platform"),
                                    rs.getBigDecimal("actual_spend"),
                                    rs.getLong("impressions"),
                                    rs.getLong("clicks"),
                                    rs.getLong("installs"),
                                    rs.getLong("registrations"),
                                    rs.getLong("first_purchases"),
                                    ids(rs.getString("account_ids")),
                                    ids(rs.getString("campaign_ids"))));
        } catch (DataAccessException exception) {
            throw new DeliveryReportException("平台数据暂不可用，请稍后重试；本次未将缺数视为零消耗", exception);
        }
    }

    /** 仅批量读取当前数据范围涉及的人员，所有过滤值使用绑定参数。 */
    @Override
    public List<com.adpulse.main.deliveryreport.DeliveryReportTypes.SpendRow> querySpend(
            LocalDate startDate, LocalDate endDate, List<String> placerIds) {
        if (placerIds.isEmpty()) return List.of();
        try {
            return jdbc.query(
                    spendSql,
                    new MapSqlParameterSource()
                            .addValue("startDate", startDate)
                            .addValue("endDate", endDate)
                            .addValue("placerIds", placerIds),
                    (rs, index) ->
                            new com.adpulse.main.deliveryreport.DeliveryReportTypes.SpendRow(
                                    rs.getDate("date").toLocalDate(), rs.getString("placer_id"),
                                    rs.getString("project_name"), rs.getString("agency_line_name"),
                                    rs.getString("platform"), rs.getBigDecimal("actual_spend")));
        } catch (DataAccessException exception) {
            throw new DeliveryReportException("平台数据暂不可用，请稍后重试；本次未将缺数视为零消耗", exception);
        }
    }

    private List<String> ids(String value) {
        if (value == null) return List.of();
        try {
            return json.readValue(value, new TypeReference<List<String>>() {}).stream()
                    .filter(id -> id != null && !id.isBlank())
                    .distinct()
                    .sorted()
                    .toList();
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("平台来源ID格式错误", exception);
        }
    }

    private static String quote(String value) {
        if (value == null || !IDENTIFIER.matcher(value).matches())
            throw new IllegalArgumentException("Doris Catalog或数据库名称不合法");
        return "`" + value + "`";
    }
}
