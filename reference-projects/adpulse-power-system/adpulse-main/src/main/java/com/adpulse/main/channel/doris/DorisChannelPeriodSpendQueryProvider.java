package com.adpulse.main.channel.doris;

import com.adpulse.main.channel.dto.ChannelRequests.ChannelPeriodSpendQuery;
import com.adpulse.main.channel.service.ChannelPeriodSpendQueryProvider;
import java.math.BigDecimal;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

/** 从 Doris 广告日明细按当前稳定渠道归属汇总 campaign 层花费。 */
@Component
@ConditionalOnProperty(prefix = "adpulse.doris", name = "enabled", havingValue = "true")
public class DorisChannelPeriodSpendQueryProvider implements ChannelPeriodSpendQueryProvider {
    private static final Pattern IDENTIFIER = Pattern.compile("[A-Za-z0-9_]+");

    private final NamedParameterJdbcTemplate jdbc;
    private final String accountTable;
    private final String channelTable;
    private final String spendTable;

    public DorisChannelPeriodSpendQueryProvider(
            DorisJdbcClient client, DorisProperties properties) {
        jdbc = client.jdbc();
        accountTable =
                qualified(
                        properties.mysqlCatalog(), properties.mysqlDatabase(), "ad_account_asset");
        channelTable =
                qualified(properties.mysqlCatalog(), properties.mysqlDatabase(), "media_channel");
        spendTable =
                qualified(properties.spendCatalog(), properties.spendDatabase(), "ad_daily_detail");
    }

    /** 日期和层级与广告面板渠道 Tab 保持一致；渠道归属使用当前资产台账的最新记录，避免迁移前后 渠道主键不同导致错配。 */
    @Override
    public Result query(ChannelPeriodSpendQuery query, int offset, int pageSize) {
        MapSqlParameterSource parameters =
                new MapSqlParameterSource()
                        .addValue("startDate", query.startDate())
                        .addValue("endDate", query.endDate())
                        .addValue("offset", offset)
                        .addValue("pageSize", pageSize);
        String channelWhere = channelWhere(query, parameters);
        String spendByChannel = spendByChannelSql();
        List<Item> items =
                jdbc.query(
                        "WITH "
                                + spendByChannel
                                + " SELECT c.id AS channel_id,"
                                + " COALESCE(s.total_consumption, 0) AS total_consumption"
                                + " FROM "
                                + channelTable
                                + " c LEFT JOIN spend_by_channel s ON s.channel_id = c.id"
                                + " WHERE "
                                + channelWhere
                                + " ORDER BY c.updated_at DESC, c.id DESC"
                                + " LIMIT :offset, :pageSize",
                        parameters,
                        (resultSet, rowNumber) ->
                                new Item(
                                        resultSet.getLong("channel_id"),
                                        resultSet.getBigDecimal("total_consumption")));
        BigDecimal total =
                jdbc.queryForObject(
                        "WITH "
                                + spendByChannel
                                + " SELECT COALESCE(SUM(s.total_consumption), 0)"
                                + " FROM "
                                + channelTable
                                + " c LEFT JOIN spend_by_channel s ON s.channel_id = c.id"
                                + " WHERE "
                                + channelWhere,
                        parameters,
                        BigDecimal.class);
        return new Result(items, total == null ? BigDecimal.ZERO : total);
    }

    private String spendByChannelSql() {
        return "latest_assets AS ("
                + " SELECT asset.channel_id, asset.account_id FROM "
                + accountTable
                + " asset WHERE asset.deleted_at = 0"
                + " AND NOT EXISTS (SELECT 1 FROM "
                + accountTable
                + " newer WHERE newer.account_id = asset.account_id"
                + " AND newer.deleted_at = 0 AND newer.id > asset.id)),"
                + " spend_by_channel AS ("
                + " SELECT asset.channel_id, SUM(spend.amount_spent) AS total_consumption"
                + " FROM latest_assets asset JOIN "
                + spendTable
                + " spend ON spend.account_id = asset.account_id"
                + " WHERE spend.`level` = 'campaign'"
                + " AND spend.`date` >= :startDate AND spend.`date` <= :endDate"
                + " GROUP BY asset.channel_id)";
    }

    private String channelWhere(ChannelPeriodSpendQuery query, MapSqlParameterSource parameters) {
        StringBuilder where = new StringBuilder("c.deleted_at = 0");
        if (hasText(query.channelName())) {
            where.append(
                    " AND (c.channel_name LIKE :channelName"
                            + " OR c.channel_short_name LIKE :channelName"
                            + " OR c.channel_code LIKE :channelName)");
            parameters.addValue("channelName", "%" + query.channelName().trim() + "%");
        }
        if (hasText(query.status())) {
            where.append(" AND c.status = :status");
            parameters.addValue("status", query.status().trim());
        }
        if (hasText(query.belongTeam())) {
            where.append(" AND c.belong_team = :belongTeam");
            parameters.addValue("belongTeam", query.belongTeam().trim());
        }
        return where.toString();
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private String qualified(String catalog, String database, String table) {
        return quote(catalog) + "." + quote(database) + "." + quote(table);
    }

    private String quote(String value) {
        if (value == null || !IDENTIFIER.matcher(value).matches()) {
            throw new IllegalArgumentException("Doris Catalog或数据库名称不合法");
        }
        return "`" + value + "`";
    }
}
